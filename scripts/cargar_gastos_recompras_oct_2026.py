"""
Carga inicial de gastos y recompras del 1 al 8 de octubre de 2026 (KOAJ
Puerto Carreño) por la API de producción. Credenciales por variables de
entorno KOAJ_EMAIL / KOAJ_PASS (no se guardan).

Uso: python cargar_octubre.py            -> solo revisa (no escribe)
     python cargar_octubre.py --ejecutar -> carga
"""
import json
import os
import sys
import urllib.request
import urllib.error

API = 'https://cierre-caja-api.onrender.com'
STORE = 'carreno'

# Saldos que deben quedar (los da el usuario)
EXPECTED_AFTER = {'cash': 862000, 'qr': 787356, 'addi_datafono': 2988503, 'nequi': 277350}

# Montos del Excel. Banco con 4x1000 incluido: valor neto + 4x1000 automático.
# Los que no dan exacto al quitar el 4x1000 van tal cual, sin 4x1000.
NO_FEE = {'apply_fee': False}
EXPENSES = [
    dict(date='2026-10-01', subcategory='arriendo', efectivo=426000,
         concept='Arriendo: se paga una parte de septiembre y la otra de octubre (total $1.110.000)'),
    dict(date='2026-10-02', subcategory='aseo', efectivo=53200,
         concept='Borrador nata, lapicero, marcador, toalla de cocina, detergente, escoba y bolsas de basura'),
    dict(date='2026-10-03', subcategory='operativo', qr=352513,
         concept='Herrajería de Carreño (una parte)',
         notes='En el Excel: $353.923 con 4x1000. Faltan $353.923; en total fueron $1.526.000 + el 4x1000, se pagó entre lo de septiembre y octubre'),
    dict(date='2026-10-05', subcategory='cuota_banco', qr=1500000,
         concept='Pago cuota Scotiabank (mamá de Angie) de septiembre'),
    dict(date='2026-10-05', subcategory='internet', qr=266000, concept='Internet de septiembre'),
    dict(date='2026-10-05', subcategory='youtube', qr=48000, concept='YouTube de septiembre'),
    dict(date='2026-10-06', subcategory='aseo', efectivo=41800, concept='Raid, jabón, Fabuloso'),
    dict(date='2026-10-07', subcategory='operativo', efectivo=3000, concept='Bolsas para clientes'),
    dict(date='2026-10-06', subcategory='luz', efectivo=318000, concept='Luz de septiembre'),
    dict(date='2026-10-08', subcategory='operativo', qr=400000,
         concept='2 esencias de Carreño y 2 de Primavera',
         notes='2 de las 4 esencias son de Primavera (no se registró como préstamo)'),
    dict(date='2026-10-08', subcategory='cuota_manejo', qr=15900, concept='Cobro cuota de manejo Bancolombia', **NO_FEE),
    dict(date='2026-10-08', subcategory='operativo', nequi=120000, concept='Humidificador Primavera',
         notes='Es de Primavera (no se registró como préstamo)', **NO_FEE),
    dict(date='2026-10-06', subcategory='operativo', datafono=1477000,
         concept='Declaración de la DIAN de Cristhian, de Carreño', **NO_FEE),
    dict(date='2026-10-08', subcategory='aseo', efectivo=7000, concept='Pañitos'),
    dict(date='2026-10-07', subcategory='alegra', datafono=139900, concept='Alegra', **NO_FEE),
]
GROUP = {'arriendo': 'operativo', 'aseo': 'operativo', 'operativo': 'operativo', 'cuota_banco': 'cuota_credito',
         'internet': 'operativo', 'youtube': 'operativo', 'luz': 'operativo', 'cuota_manejo': 'financiero',
         'alegra': 'operativo'}

# Recompras: el efectivo no paga 4x1000 (fee_override=0); el QR lleva el
# 4x1000 automático encima de lo que le llega a Jhonatan.
REPURCHASES = [
    dict(date='2026-10-05', efectivo=2710000, fee_override=0),
    dict(date='2026-10-06', qr=2200000, notes='En el Excel: $2.208.800 con 4x1000'),
    dict(date='2026-10-07', qr=1040000, notes='En el Excel: $1.044.160 con 4x1000'),
    dict(date='2026-10-07', qr=307500, notes='En el Excel: $308.730 con 4x1000'),
    dict(date='2026-10-07', efectivo=2998000, fee_override=0),
    dict(date='2026-10-07', efectivo=717400, fee_override=0),
]


def call(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Content-Type', 'application/json')
    req.add_header('X-Store', STORE)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def balances(token):
    st, data = call('GET', '/api/accounts', token)
    assert st == 200, data
    return {a['payment_key']: a['balance'] for a in data['accounts']}


def main():
    """
    Estado al 9-oct-2026 noche: las 6 recompras ya están (3 de efectivo que
    había, con el 4x1000 corregido a 0, y las 3 de QR cargadas). Falta, con la
    versión nueva desplegada: los 15 gastos y un ajuste en EFECTIVO que anula
    el ajuste de más del 9-oct (las 3 recompras de efectivo ya estaban
    descontadas) para que quede en 862.000.
    """
    run = '--ejecutar' in sys.argv
    st, data = call('POST', '/auth/login', body={'email': os.environ['KOAJ_EMAIL'], 'password': os.environ['KOAJ_PASS']})
    assert st == 200 and data.get('token'), f'Login falló: {st} {data.get("message")}'
    token = data['token']

    st, exp_data = call('GET', '/api/expenses?year=2026&month=10', token)
    st2, rep_data = call('GET', '/api/repurchase?year=2026&month=10', token)
    reps = rep_data.get('entries', [])
    print(f"Octubre: {len(exp_data.get('items', []))} gastos, {len(reps)} recompras")

    before = balances(token)
    key = {'efectivo': 'cash', 'qr': 'qr', 'datafono': 'addi_datafono', 'nequi': 'nequi'}
    out = {k: 0.0 for k in EXPECTED_AFTER}
    for e in EXPENSES:
        for m, k in key.items():
            amt = e.get(m, 0)
            if amt:
                out[k] += amt + (0 if (m == 'efectivo' or e.get('apply_fee') is False) else round(amt * 4 / 1000))
    adjust = EXPECTED_AFTER['cash'] - (before['cash'] - out['cash'])
    print(f"Ajuste EFECTIVO: {adjust:,.0f} (esperado -6.440.262)")
    for k, exp in EXPECTED_AFTER.items():
        after = before.get(k, 0) - out[k] + (adjust if k == 'cash' else 0)
        print(f'{k:14} {before.get(k, 0):>11,.0f} -> {after:>11,.0f}  esperado {exp:>11,.0f}{"" if round(after) == exp else "  <-- NO CUADRA"}')
    if not run:
        print('Solo revisión. Para cargar: --ejecutar')
        return
    if exp_data.get('items') or len(reps) != 6 or round(adjust) != -6440262:
        sys.exit('No se carga: ya hay gastos, no están las 6 recompras o el ajuste no es el esperado.')

    for i, e in enumerate(EXPENSES):
        body = {'direction': 'out', 'period': '2026-10', 'account_mode': 'cuentas',
                'category': GROUP[e['subcategory']], **e}
        st, data = call('POST', '/api/expenses', token, body)
        assert st == 201, (e['concept'], data)
        if i == 0 and 'subcategory' not in data['item']:
            call('DELETE', f"/api/expenses/{data['item']['id']}", token)
            sys.exit('Producción todavía no tiene la versión nueva (falta Manual Deploy). Se borró el gasto de prueba.')
        print('gasto ok', e['date'], e['concept'][:50], data['item']['total_with_fee'])

    cash_id = next(a['id'] for a in call('GET', '/api/accounts', token)[1]['accounts'] if a['payment_key'] == 'cash')
    st, data = call('POST', '/api/accounts/manual-adjustment', token, {
        'account_id': cash_id, 'direction': 'out', 'amount': -adjust,
        'description': 'Corrige el ajuste del 9-oct: las 3 recompras en efectivo (5 y 7-oct) ya estaban descontadas'})
    assert st in (200, 201), data
    after = balances(token)
    print('\nSaldos finales:')
    for k, exp in EXPECTED_AFTER.items():
        print(f'{k:14} {after.get(k, 0):>11,.0f}  esperado {exp:>11,.0f}{"" if round(after.get(k, 0)) == exp else "  <-- NO CUADRA"}')


if __name__ == '__main__':
    main()
