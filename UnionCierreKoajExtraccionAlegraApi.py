# ExtraccionJsonAlegra.py
from flask import Flask, request, jsonify
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone, timedelta

# Intentar usar zoneinfo; si no está disponible, caer al fallback UTC-5
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    HAVE_ZONEINFO = True
except Exception:
    ZoneInfo = None
    HAVE_ZONEINFO = False

app = Flask(__name__)

# Usuario por defecto (opcional)
DEFAULT_USERNAME = "koaj.puertocarreno@gmail.com"

# Denominaciones
DENOMINACIONES_MONEDAS = [50, 100, 200, 500, 1000]
DENOMINACIONES_BILLETES = [2000, 5000, 10000, 20000, 50000, 100000]

# Constantes caja
OBJ_BASE = 450000
UMBRAL_MENUDO = 10000

# ---------------- utilidades ----------------
def safe_int(x):
    try:
        return int(x)
    except Exception:
        try:
            return int(float(x))
        except Exception:
            return 0

def safe_number(amount):
    if amount is None:
        return 0
    if isinstance(amount, (int, float)):
        return amount
    try:
        s = str(amount).replace(",", "").strip()
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        try:
            return float(str(amount))
        except Exception:
            return 0

def format_cop(amount):
    try:
        formatted = f"{int(round(amount, 0)):,}".replace(",", ".")
        return f"${formatted}"
    except Exception:
        return f"${amount}"

def normalize_method(pm: str) -> str:
    if not pm:
        return "other"
    pm_low = pm.lower()
    if "credit" in pm_low:
        return "credit-card"
    if "debit" in pm_low:
        return "debit-card"
    if "transfer" in pm_low:
        return "transfer"
    if "cash" in pm_low:
        return "cash"
    return "other"

# ---------------- conteo / base algorithms ----------------
def descomponer_binario(valor, cantidad):
    partes = []
    k = 1
    restante = cantidad
    while k <= restante:
        partes.append(k)
        restante -= k
        k *= 2
    if restante > 0:
        partes.append(restante)
    return partes

def construir_base_exacta(todas_denoms, monto_objetivo, umbral_menudo=UMBRAL_MENUDO):
    """
    Bounded knapsack via binary splitting to try to get EXACT base.
    Returns: conteo_base (dict), conteo_consignar (dict), restante (int), exacto (bool)
    """
    MAX = monto_objetivo
    NEG = -10**18
    dp = [NEG] * (MAX + 1)
    dp[0] = 0
    prev = [None] * (MAX + 1)

    items = []
    for denom, cnt in todas_denoms.items():
        if cnt <= 0:
            continue
        partes = descomponer_binario(denom, cnt)
        for k in partes:
            valor_total = denom * k
            aporte_menudo = valor_total if denom <= umbral_menudo else 0
            items.append((valor_total, aporte_menudo, denom, k))

    for valor_total, aporte_menudo, denom, k in items:
        for s in range(MAX, valor_total - 1, -1):
            if dp[s - valor_total] != NEG:
                cand = dp[s - valor_total] + aporte_menudo
                if cand > dp[s]:
                    dp[s] = cand
                    prev[s] = (s - valor_total, denom, k)

    if dp[MAX] != NEG:
        usado = {}
        s = MAX
        while s > 0:
            entry = prev[s]
            if entry is None:
                break
            s_prev, denom, k = entry
            usado[denom] = usado.get(denom, 0) + k
            s = s_prev
        conteo_base = {d: usado.get(d, 0) for d in todas_denoms}
        conteo_consignar = {d: todas_denoms[d] - conteo_base[d] for d in todas_denoms}
        restante = 0
        return conteo_base, conteo_consignar, restante, True

    mejor_s = -1
    for s in range(MAX, -1, -1):
        if dp[s] != NEG:
            mejor_s = s
            break

    if mejor_s == -1:
        conteo_base = {d: 0 for d in todas_denoms}
        conteo_consignar = dict(todas_denoms)
        restante = monto_objetivo
        return conteo_base, conteo_consignar, restante, False

    usado = {}
    s = mejor_s
    while s > 0:
        entry = prev[s]
        if entry is None:
            break
        s_prev, denom, k = entry
        usado[denom] = usado.get(denom, 0) + k
        s = s_prev
    conteo_base = {d: usado.get(d, 0) for d in todas_denoms}
    conteo_consignar = {d: todas_denoms[d] - conteo_base[d] for d in todas_denoms}
    restante = monto_objetivo - mejor_s
    return conteo_base, conteo_consignar, restante, False

# ---------------- procesamiento de facturas (Alegra) ----------------
def process_invoices(invoices):
    totals = {
        "credit-card": 0,
        "debit-card": 0,
        "transfer": 0,
        "cash": 0
    }
    for inv in invoices:
        payments = inv.get("payments", []) or []
        for p in payments:
            amount = safe_number(p.get("amount"))
            pm_raw = p.get("paymentMethod", "")
            method = normalize_method(pm_raw)
            if method in totals:
                totals[method] += amount
    return totals

def build_alegra_struct(totals, date, username):
    labels = {
        "credit-card": "Tarjeta crédito",
        "debit-card": "Tarjeta débito",
        "transfer": "Transferencia",
        "cash": "Efectivo"
    }
    result = {}
    for k, v in totals.items():
        result[k] = {
            "label": labels.get(k, k),
            "total": int(v),
            "formatted": format_cop(v)
        }
    total_sum = sum(totals.get(k, 0) for k in ["credit-card", "debit-card", "transfer", "cash"])
    result_total = {
        "label": "TOTAL VENTA DEL DÍA",
        "total": int(total_sum),
        "formatted": format_cop(total_sum)
    }
    return {
        "date_requested": date,
        "username_used": username,
        "results": result,
        "total_sale": result_total
    }

# ---------------- endpoint ----------------
@app.route("/sum_payments", methods=["POST"])
def sum_payments_post():
    """
    JSON esperado (ejemplo):
    {
      "date": "2025-10-09",
      "password": "0990...",
      "username": "opcional@mail.com",
      "coins": {"50": 10, "100": 5, ...},
      "bills": {"2000": 3, "5000": 0, ...},
      "excedente": 0,
      "gastos_operativos": 0,
      "prestamos": 0
    }
    """
    # timestamp de la petición: usar ZoneInfo si está, sino fallback UTC-5
    if HAVE_ZONEINFO:
        try:
            now = datetime.now(ZoneInfo("America/Bogota"))
            tz_used = "America/Bogota"
        except Exception:
            # zoneinfo presente pero no se pudo cargar la zona: fallback a UTC-5
            now = datetime.now(timezone(timedelta(hours=-5)))
            tz_used = "UTC-05:00 (fallback)"
    else:
        now = datetime.now(timezone(timedelta(hours=-5)))
        tz_used = "UTC-05:00 (fallback)"

    request_datetime = now.isoformat()
    request_date = now.date().isoformat()
    request_time = now.strftime("%H:%M:%S")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Debe enviar JSON en el body con 'date' y 'password'."}), 400

    date = data.get("date")
    password = data.get("password")
    username = data.get("username", DEFAULT_USERNAME)

    if not date or not password:
        return jsonify({"error": "Faltan campos obligatorios: 'date' y/o 'password'."}), 400

    # ----------------- leer conteos enviados (pueden faltar) -----------------
    coins_input = data.get("coins", {}) or {}
    bills_input = data.get("bills", {}) or {}

    # Normalizar keys a ints y asegurar todas las denominaciones estén presentes
    conteo_monedas = {}
    for d in DENOMINACIONES_MONEDAS:
        conteo_monedas[d] = safe_int(coins_input.get(str(d), coins_input.get(d, 0)))

    conteo_billetes = {}
    for d in DENOMINACIONES_BILLETES:
        conteo_billetes[d] = safe_int(bills_input.get(str(d), bills_input.get(d, 0)))

    # extras
    excedente = safe_number(data.get("excedente", 0))
    gastos_operativos = safe_number(data.get("gastos_operativos", 0))
    prestamos = safe_number(data.get("prestamos", 0))

    # ----------------- cálculos totales físicos -----------------
    total_monedas = sum(d * c for d, c in conteo_monedas.items())
    total_billetes = sum(d * c for d, c in conteo_billetes.items())
    total_general = total_monedas + total_billetes

    todas_denoms = {**{d: conteo_monedas.get(d, 0) for d in DENOMINACIONES_MONEDAS},
                    **{d: conteo_billetes.get(d, 0) for d in DENOMINACIONES_BILLETES}}

    conteo_base, conteo_consignar, restante_base, exacto = construir_base_exacta(todas_denoms, OBJ_BASE, UMBRAL_MENUDO)

    base_monedas = {d: conteo_base.get(d, 0) for d in DENOMINACIONES_MONEDAS}
    base_billetes = {d: conteo_base.get(d, 0) for d in DENOMINACIONES_BILLETES}
    consignar_monedas = {d: conteo_consignar.get(d, 0) for d in DENOMINACIONES_MONEDAS}
    consignar_billetes = {d: conteo_consignar.get(d, 0) for d in DENOMINACIONES_BILLETES}

    total_base_monedas = sum(d * c for d, c in base_monedas.items())
    total_base_billetes = sum(d * c for d, c in base_billetes.items())
    total_base = total_base_monedas + total_base_billetes

    total_consignar_sin_ajustes = sum(d * c for d, c in consignar_monedas.items()) + sum(d * c for d, c in consignar_billetes.items())
    efectivo_para_consignar_final = total_consignar_sin_ajustes - gastos_operativos - prestamos

    # VENTA EFECTIVO DIARIA | ALEGRA = TOTAL_GENERAL - EXCEDENTE - BASE
    venta_efectivo_diaria_alegra = total_general - excedente - total_base

    # ----------------- petición a Alegra -----------------
    url = f"https://api.alegra.com/api/v1/invoices?date={date}"
    try:
        resp = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=20)
    except Exception as e:
        return jsonify({"error": f"Error al contactar Alegra: {e}"}), 500

    if resp.status_code != 200:
        # devolver info de caja igualmente para debugging
        partial = {
            "request_datetime": request_datetime,
            "request_date": request_date,
            "request_time": request_time,
            "request_tz": tz_used,
            "cash_count": {
                "input_coins": conteo_monedas,
                "input_bills": conteo_billetes,
                "totals": {
                    "total_monedas": int(total_monedas),
                    "total_billetes": int(total_billetes),
                    "total_general": int(total_general)
                },
                "base": {
                    "base_monedas": base_monedas,
                    "base_billetes": base_billetes,
                    "total_base_monedas": int(total_base_monedas),
                    "total_base_billetes": int(total_base_billetes),
                    "total_base": int(total_base)
                },
                "consignar": {
                    "consignar_monedas": consignar_monedas,
                    "consignar_billetes": consignar_billetes,
                    "total_consignar_sin_ajustes": int(total_consignar_sin_ajustes),
                    "efectivo_para_consignar_final": int(efectivo_para_consignar_final)
                },
                "adjustments": {
                    "excedente": int(excedente),
                    "gastos_operativos": int(gastos_operativos),
                    "prestamos": int(prestamos),
                    "venta_efectivo_diaria_alegra": int(venta_efectivo_diaria_alegra)
                }
            },
            "alegra": {
                "error": "Respuesta no exitosa desde Alegra",
                "status_code": resp.status_code,
                "body": resp.text
            }
        }
        return jsonify(partial), 502

    try:
        invoices = resp.json()
    except Exception as e:
        return jsonify({"error": f"No se pudo parsear JSON de Alegra: {e}"}), 500

    alegra_totals = process_invoices(invoices)
    alegra_struct = build_alegra_struct(alegra_totals, date, username)

    # ----------------- construir respuesta final -----------------
    cash_section = {
        "input_coins": conteo_monedas,
        "input_bills": conteo_billetes,
        "totals": {
            "total_monedas": int(total_monedas),
            "total_billetes": int(total_billetes),
            "total_general": int(total_general),
            "total_general_formatted": format_cop(total_general)
        },
        "base": {
            "base_monedas": base_monedas,
            "base_billetes": base_billetes,
            "total_base_monedas": int(total_base_monedas),
            "total_base_billetes": int(total_base_billetes),
            "total_base": int(total_base),
            "total_base_formatted": format_cop(total_base),
            "exact_base_obtained": bool(exacto),
            "restante_para_base": int(restante_base)
        },
        "consignar": {
            "consignar_monedas": consignar_monedas,
            "consignar_billetes": consignar_billetes,
            "total_consignar_sin_ajustes": int(total_consignar_sin_ajustes),
            "total_consignar_sin_ajustes_formatted": format_cop(total_consignar_sin_ajustes),
            "efectivo_para_consignar_final": int(efectivo_para_consignar_final),
            "efectivo_para_consignar_final_formatted": format_cop(efectivo_para_consignar_final)
        },
        "adjustments": {
            "excedente": int(excedente),
            "excedente_formatted": format_cop(excedente),
            "gastos_operativos": int(gastos_operativos),
            "gastos_operativos_formatted": format_cop(gastos_operativos),
            "prestamos": int(prestamos),
            "prestamos_formatted": format_cop(prestamos),
            "venta_efectivo_diaria_alegra": int(venta_efectivo_diaria_alegra),
            "venta_efectivo_diaria_alegra_formatted": format_cop(venta_efectivo_diaria_alegra)
        }
    }

    response = {
        "request_datetime": request_datetime,
        "request_date": request_date,
        "request_time": request_time,
        "request_tz": tz_used,
        "date_requested": date,
        "username_used": username,
        "cash_count": cash_section,
        "alegra": alegra_struct
    }

    # imprimir en consola para debug
    print("Request POST", date, username)
    print("  Timestamp:", request_datetime, f"({request_date} {request_time})", "TZ:", tz_used)
    print("  Totales caja:", format_cop(total_general))
    print("  Ajustes: excedente", format_cop(excedente), "gastos", format_cop(gastos_operativos), "prestamos", format_cop(prestamos))
    print("  Venta efectivo (Alegra formula):", format_cop(venta_efectivo_diaria_alegra))
    for k in alegra_totals:
        print(f"  {k}: {format_cop(alegra_totals[k])}")
    print(f"  TOTAL VENTA DEL DÍA: {format_cop(sum(alegra_totals.values()))}")

    return jsonify(response), 200

if __name__ == "__main__":
    # Ejecutar servidor Flask en 0.0.0.0:5000
    app.run(host="0.0.0.0", port=5000, debug=True)
