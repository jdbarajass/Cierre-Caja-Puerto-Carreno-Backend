"""
Rutas del módulo Cuentas: saldo por medio de pago, ajustes manuales,
transferencias entre cuentas y sincronización automática con el cierre de caja.
Acceso: solo admin (igual que Cuentas Recompras).
"""
import uuid
import hmac
import logging
from functools import wraps
from datetime import datetime

from flask import Blueprint, request, jsonify, g

from app.middlewares.auth import token_required, role_required, get_current_user
from app.models.user import db
from app.models.account import Account, AccountMovement
from app.models.cash_closing import CashClosing
from app.config import Config
from app.utils.timezone import get_colombia_now, parse_colombia_date
from app.services.alegra_client import AlegraClient
from app.exceptions import AlegraConnectionError

logger = logging.getLogger(__name__)
bp = Blueprint('accounts', __name__)

# Cuentas por defecto (payment_key -> nombre/color), sembradas una sola vez si la
# tabla está vacía. El campo de cierre de caja que acredita cada una se resuelve
# en sync_daily().
DEFAULT_ACCOUNTS = [
    {'payment_key': 'cash', 'name': 'EFECTIVO', 'color': 'green', 'sort_order': 1},
    {'payment_key': 'nequi', 'name': 'NEQUI', 'color': 'purple', 'sort_order': 2},
    {'payment_key': 'daviplata', 'name': 'DAVIPLATA', 'color': 'red', 'sort_order': 3},
    {'payment_key': 'qr', 'name': 'QR BANCOLOMBIA', 'color': 'orange', 'sort_order': 4},
    {'payment_key': 'addi_datafono', 'name': 'ADDI + DATÁFONO (Tarjetas)', 'color': 'blue', 'sort_order': 5},
    {'payment_key': 'sistecredito', 'name': 'SisteCrédito', 'color': 'teal', 'sort_order': 6},
    {'payment_key': 'bbva', 'name': 'BBVA', 'color': 'indigo', 'sort_order': 7},
]


def seed_default_accounts():
    """
    Inserta las cuentas por defecto que falten. Idempotente y no destructivo:
    nunca borra ni modifica cuentas existentes (ni su saldo), solo agrega las
    que falten - así se pueden sumar cuentas nuevas (ej. BBVA) en despliegues
    futuros sin afectar las que ya están en producción con saldo real.
    """
    existing_keys = {a.payment_key for a in Account.query.all()}
    missing = [data for data in DEFAULT_ACCOUNTS if data['payment_key'] not in existing_keys]
    if not missing:
        return
    for data in missing:
        db.session.add(Account(balance=0, active=True, **data))
    db.session.commit()
    logger.info(f"Cuentas por defecto creadas: {[m['name'] for m in missing]}")


def sync_token_or_admin_required(f):
    """
    Permite acceder si:
      - el header X-Sync-Token coincide con Config.DAILY_SYNC_TOKEN (no vacío), o
      - hay un JWT válido de un usuario con rol admin.
    Así GitHub Actions puede llamar el endpoint sin loguearse, y si el token
    no está configurado el endpoint sigue protegido por JWT admin.
    """
    admin_only = token_required(role_required('admin')(f))

    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return '', 204

        sync_token = request.headers.get('X-Sync-Token')
        # hmac.compare_digest evita filtrar por timing cuánto del token coincide
        if Config.DAILY_SYNC_TOKEN and sync_token and hmac.compare_digest(sync_token, Config.DAILY_SYNC_TOKEN):
            g.current_user = {'userId': None, 'email': 'daily-sync-job', 'role': 'admin'}
            return f(*args, **kwargs)

        # Fallback: exigir JWT admin normal (mismo decorador que usan los demás módulos)
        return admin_only(*args, **kwargs)

    return decorated


# ─────────────────────────────────────────────
#  LISTAR CUENTAS
# ─────────────────────────────────────────────

@bp.route('/api/accounts', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def list_accounts():
    if request.method == 'OPTIONS':
        return '', 204

    accounts = Account.query.filter_by(active=True).order_by(Account.sort_order.asc()).all()
    total_balance = sum(a.balance for a in accounts)

    return jsonify({
        'success': True,
        'accounts': [a.to_dict() for a in accounts],
        'total_balance': total_balance
    }), 200


# ─────────────────────────────────────────────
#  MOVIMIENTOS
# ─────────────────────────────────────────────

@bp.route('/api/accounts/movements', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def list_movements():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        q = AccountMovement.query

        account_id = request.args.get('account_id', type=int)
        if account_id:
            q = q.filter(AccountMovement.account_id == account_id)

        movement_type = request.args.get('type')
        if movement_type:
            q = q.filter(AccountMovement.type == movement_type)

        start_date = request.args.get('start_date')
        if start_date:
            q = q.filter(AccountMovement.created_at >= parse_colombia_date(start_date))

        end_date = request.args.get('end_date')
        if end_date:
            from datetime import timedelta
            end_dt = parse_colombia_date(end_date) + timedelta(days=1)
            q = q.filter(AccountMovement.created_at < end_dt)

        limit = request.args.get('limit', default=200, type=int)
        movements = q.order_by(AccountMovement.created_at.desc()).limit(limit).all()

        return jsonify({
            'success': True,
            'movements': [m.to_dict() for m in movements],
            'count': len(movements)
        }), 200

    except Exception as e:
        logger.error(f"Error listando movimientos: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener movimientos'}), 500


# ─────────────────────────────────────────────
#  AJUSTE MANUAL
# ─────────────────────────────────────────────

@bp.route('/api/accounts/manual-adjustment', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def manual_adjustment():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json() or {}

        account_id = data.get('account_id')
        amount = data.get('amount')
        direction = data.get('direction')  # 'in' | 'out'
        description = (data.get('description') or '').strip() or None

        if not account_id or amount is None or direction not in ('in', 'out'):
            return jsonify({
                'success': False,
                'message': 'Campos requeridos: account_id, amount, direction ("in" o "out")'
            }), 400

        amount = float(amount)
        if amount <= 0:
            return jsonify({'success': False, 'message': 'El monto debe ser mayor a 0'}), 400

        # Bloquea la fila para que un ajuste y una transferencia concurrentes
        # sobre la misma cuenta no lean el mismo balance antes de que ninguno
        # de los dos haga commit (evita corromper el saldo).
        account = Account.query.with_for_update().get(account_id)
        if not account:
            return jsonify({'success': False, 'message': 'Cuenta no encontrada'}), 404

        signed_amount = amount if direction == 'in' else -amount

        movement = AccountMovement(
            account_id=account.id,
            type='manual_adjustment',
            amount=signed_amount,
            description=description,
            created_by=get_current_user().get('userId')
        )
        account.balance += signed_amount

        db.session.add(movement)
        db.session.commit()

        logger.info(f"Ajuste manual: cuenta={account.name} monto={signed_amount}")
        return jsonify({
            'success': True,
            'account': account.to_dict(),
            'movement': movement.to_dict()
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en ajuste manual: {e}")
        return jsonify({'success': False, 'message': 'Error al registrar el ajuste'}), 500


# ─────────────────────────────────────────────
#  TRANSFERIR ENTRE CUENTAS
# ─────────────────────────────────────────────

@bp.route('/api/accounts/transfer', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def transfer():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json() or {}

        from_account_id = data.get('from_account_id')
        to_account_id = data.get('to_account_id')
        amount = data.get('amount')
        description = (data.get('description') or '').strip() or None

        if not from_account_id or not to_account_id or amount is None:
            return jsonify({
                'success': False,
                'message': 'Campos requeridos: from_account_id, to_account_id, amount'
            }), 400

        if from_account_id == to_account_id:
            return jsonify({'success': False, 'message': 'La cuenta origen y destino deben ser distintas'}), 400

        amount = float(amount)
        if amount <= 0:
            return jsonify({'success': False, 'message': 'El monto debe ser mayor a 0'}), 400

        # Bloquea ambas filas (siempre en el mismo orden por id, para que dos
        # transferencias concurrentes en direcciones opuestas no se bloqueen
        # mutuamente) antes de leer/mutar balance, para que dos transferencias
        # simultáneas desde la misma cuenta no puedan dejarla en negativo.
        first_id, second_id = sorted([int(from_account_id), int(to_account_id)])
        locked_by_id = {
            a.id: a for a in Account.query.filter(Account.id.in_([first_id, second_id]))
            .with_for_update().order_by(Account.id.asc()).all()
        }
        from_account = locked_by_id.get(int(from_account_id))
        to_account = locked_by_id.get(int(to_account_id))
        if not from_account or not to_account:
            return jsonify({'success': False, 'message': 'Cuenta no encontrada'}), 404

        if from_account.balance < amount:
            return jsonify({'success': False, 'message': 'Saldo insuficiente en la cuenta origen'}), 400

        reference_id = uuid.uuid4().hex
        user_id = get_current_user().get('userId')

        from_account.balance -= amount
        to_account.balance += amount

        movement_out = AccountMovement(
            account_id=from_account.id,
            type='transfer_out',
            amount=-amount,
            description=description,
            reference_id=reference_id,
            created_by=user_id
        )
        movement_in = AccountMovement(
            account_id=to_account.id,
            type='transfer_in',
            amount=amount,
            description=description,
            reference_id=reference_id,
            created_by=user_id
        )

        db.session.add(movement_out)
        db.session.add(movement_in)
        db.session.commit()

        logger.info(f"Transferencia: {from_account.name} -> {to_account.name} monto={amount}")
        return jsonify({
            'success': True,
            'from_account': from_account.to_dict(),
            'to_account': to_account.to_dict(),
            'reference_id': reference_id
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en transferencia: {e}")
        return jsonify({'success': False, 'message': 'Error al registrar la transferencia'}), 500


# ─────────────────────────────────────────────
#  SINCRONIZACIÓN DIARIA (job de las 9pm / botón "Sincronizar ahora")
# ─────────────────────────────────────────────

@bp.route('/api/accounts/sync-daily', methods=['POST', 'OPTIONS'])
@sync_token_or_admin_required
def sync_daily():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json(silent=True) or {}
        date_str = data.get('date')
        if not date_str:
            date_str = get_colombia_now().strftime('%Y-%m-%d')

        closing_date = parse_colombia_date(date_str).date()

        closing = CashClosing.query.filter_by(closing_date=closing_date).first()
        if not closing:
            return jsonify({
                'success': False,
                'message': f'No hay cierre de caja registrado para {date_str}'
            }), 404

        # "Claim" atómico: un UPDATE condicionado a synced_to_accounts=False solo
        # puede tener éxito para UNA de dos peticiones concurrentes (ej. el cron
        # de las 9pm y un click en "Sincronizar ahora" al mismo tiempo, o un
        # reintento del workflow de GitHub Actions) - evita acreditar el mismo
        # cierre dos veces. rows_claimed==0 significa que ya estaba sincronizado
        # (por esta u otra petición concurrente que ganó la carrera).
        claim_time = datetime.utcnow()
        rows_claimed = CashClosing.query.filter_by(
            id=closing.id, synced_to_accounts=False
        ).update({'synced_to_accounts': True, 'synced_at': claim_time}, synchronize_session=False)
        db.session.commit()

        if rows_claimed == 0:
            db.session.refresh(closing)
            return jsonify({
                'success': True,
                'message': 'Este cierre ya fue sincronizado anteriormente, no se duplica.',
                'synced_at': closing.to_dict()['synced_at'],
                'cash_closing': closing.to_dict()
            }), 200

        # Mapeo cuenta <- campo del cierre (ver plan: usa los mismos campos que
        # ya llena la vendedora en el cierre de caja diario)
        credit_map = [
            ('cash', closing.efectivo),
            ('nequi', closing.nequi),
            ('daviplata', closing.daviplata),
            ('qr', closing.qr),
            ('addi_datafono', closing.addi_datafono),
        ]

        accounts_by_key = {a.payment_key: a for a in Account.query.filter(
            Account.payment_key.in_([k for k, _ in credit_map])
        ).all()}

        credited = []
        user_id = get_current_user().get('userId') if get_current_user() else None

        for payment_key, amount in credit_map:
            if not amount:
                continue
            account = accounts_by_key.get(payment_key)
            if not account:
                logger.warning(f"sync_daily: no existe cuenta con payment_key={payment_key}, se omite")
                continue

            movement = AccountMovement(
                account_id=account.id,
                type='cash_closing',
                amount=amount,
                description=f'Cierre de caja {date_str}',
                cash_closing_id=closing.id,
                created_by=user_id
            )
            account.balance += amount
            db.session.add(movement)
            credited.append({'account': account.name, 'amount': amount})

        # Verificación contra Alegra (no bloquea, solo informa)
        discrepancy = None
        try:
            client = AlegraClient(Config.ALEGRA_USER, Config.ALEGRA_PASS, Config.ALEGRA_API_BASE_URL, Config.ALEGRA_TIMEOUT)
            alegra_summary = client.get_sales_summary(date_str)
            results = alegra_summary.get('results', {})

            alegra_cash = results.get('cash', {}).get('total', 0)
            alegra_transfer = results.get('transfer', {}).get('total', 0)
            alegra_cards = results.get('debit-card', {}).get('total', 0) + results.get('credit-card', {}).get('total', 0)

            closing.alegra_total_efectivo = alegra_cash
            closing.alegra_total_transferencia = alegra_transfer
            closing.alegra_total_tarjeta = alegra_cards

            # Comparación: efectivo del cierre vs efectivo Alegra, y
            # (nequi+daviplata+qr+addi_datafono) del cierre vs (transfer+tarjetas) de Alegra
            registrado_efectivo = closing.efectivo
            registrado_digital = closing.nequi + closing.daviplata + closing.qr + closing.addi_datafono
            alegra_digital = alegra_transfer + alegra_cards

            discrepancy = (registrado_efectivo - alegra_cash) + (registrado_digital - alegra_digital)
            closing.alegra_discrepancy = discrepancy
            closing.alegra_checked = True

        except AlegraConnectionError as e:
            logger.warning(f"sync_daily: no se pudo verificar contra Alegra para {date_str}: {e}")
        except Exception as e:
            logger.warning(f"sync_daily: error inesperado verificando Alegra para {date_str}: {e}")

        # Reflejar en el objeto en memoria lo que el UPDATE atómico de arriba ya
        # dejó en la base de datos (query.update() no refresca la instancia ORM).
        closing.synced_to_accounts = True
        closing.synced_at = claim_time

        db.session.commit()

        logger.info(f"sync_daily completado para {date_str}: {credited}, discrepancia={discrepancy}")

        return jsonify({
            'success': True,
            'date': date_str,
            'credited': credited,
            'alegra_discrepancy': discrepancy,
            'cash_closing': closing.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en sync_daily: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Error al sincronizar las cuentas'}), 500
