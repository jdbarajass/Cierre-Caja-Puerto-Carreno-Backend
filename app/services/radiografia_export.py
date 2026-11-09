"""
Radiografía, Fase 6: exportar a Excel y PDF (docs/PLAN_RADIOGRAFIA.md).

El archivo sale de los MISMOS datos que la pantalla (la respuesta de cada
vista), no se recalcula nada. Cada vista se convierte en un "reporte":
secciones con columnas, filas y formato por columna, más una lista de notas
(avisos de la pantalla, fórmulas y qué es ESTIMADO). Después ese reporte se
dibuja en Excel (openpyxl: una hoja con todo + hoja de Notas; las listas
largas en su propia hoja) o en PDF (reportlab, horizontal).

Formatos de celda: 'text', 'money', 'pct', 'num', 'date'. None → "—". Un
texto en una columna de números (ej. "sin gastos") se deja como texto.
"""
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

MONEY, PCT, NUM, TEXT, DATE = 'money', 'pct', 'num', 'text', 'date'
EST = ' (ESTIMADO)'
NOTE_ESTIMADO = ('ESTIMADO: el costo de la ropa es el precio de lista × (1 − margen KOAJ), porque en Alegra el costo '
                 'es igual al precio de venta. Todo lo que depende de ese costo (utilidad bruta, utilidad neta, '
                 'inventario a costo, punto de equilibrio, falta por recomprar) es una estimación.')
NOTE_REGISTRADO = 'Solo se resta lo que se registró a mano (gastos, cuotas, pagos); lo pendiente va como aviso.'


def section(title: str, columns: List[str], formats: List[str], rows: List[List[Any]],
            own_sheet: bool = False) -> Dict[str, Any]:
    return {'title': title, 'columns': columns, 'formats': formats, 'rows': rows, 'own_sheet': own_sheet}


# ─────────────────────────────────────────────
#  Texto de una celda (PDF y celdas que no son número)
# ─────────────────────────────────────────────

def cop(v: float) -> str:
    return ('-' if v < 0 else '') + '$ ' + f'{abs(round(v)):,}'.replace(',', '.')


def as_text(v: Any, kind: str) -> str:
    if v is None:
        return '—'
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return 'Sí' if v else 'No'
    if kind == MONEY:
        return cop(v)
    if kind == PCT:
        return f'{v * 100:.1f} %'.replace('.', ',')
    if kind == NUM:
        return f'{v:,.0f}'.replace(',', '.') if float(v).is_integer() else f'{v:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    if kind == DATE and isinstance(v, str):
        return v
    return str(v)


def _d(iso: Optional[str]) -> str:
    return f'{iso[8:10]}/{iso[5:7]}/{iso[:4]}' if iso else '—'


# ─────────────────────────────────────────────
#  Vista → reporte
# ─────────────────────────────────────────────

STATEMENT = [
    ('ventas', 'Ventas netas', 'Facturas de Alegra no anuladas (igual que Cuentas → Año)', False, True),
    ('precio_lista', 'Precio de lista vendido', 'Ropa (cantidad × precio de lista) + tarjetas regalo vendidas; sin bolsas', False, False),
    ('descuentos', 'Descuentos', 'Precio de lista vendido + bolsas − ventas netas', False, False),
    ('costo_estimado', 'Costo de la ropa', 'Precio de lista vendido × (1 − margen KOAJ)', True, False),
    ('fletes', 'Fletes y moto carro', 'Salidas de flete del mes (con 4x1000)', False, False),
    ('costo_vendido', 'Costo de lo vendido', 'Costo de la ropa + fletes', True, False),
    ('utilidad_bruta', 'Utilidad bruta', 'Ventas netas − costo de lo vendido', True, True),
    ('gastos_operativos', 'Gastos operativos', 'Operativo + sueldos + otro, del mes al que corresponden', False, False),
    ('utilidad_operacional', 'Utilidad operacional', 'Utilidad bruta − gastos operativos', True, True),
    ('gastos_financieros', 'Gastos financieros', '4x1000 (gastos y recompras) + intereses de las cuotas + comisiones', False, False),
    ('utilidad_neta', 'Utilidad neta (antes de impuestos)', 'Utilidad operacional − gastos financieros', True, True),
    ('cuotas', 'Cuotas de crédito (capital)', 'No baja la utilidad (es devolver un préstamo), pero la plata sale', False, False),
    ('recompras', 'Recompras enviadas', 'Lo enviado a Jhonatan en el mes', False, False),
    ('lo_que_quedo', 'Lo que quedó', 'Ventas − recompras − gastos − cuotas (= ganancia real de Cuentas → Año)', False, True),
]
NEEDS_EXPENSES = ('gastos_operativos', 'utilidad_operacional', 'gastos_financieros', 'utilidad_neta')


def month_report(m: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    title = f'Radiografía del mes · {store_name}'
    sub = m.get('label', m['period']).capitalize()
    if m.get('future'):
        return {'title': title, 'subtitle': sub, 'sections': [], 'notes': ['Ese mes todavía no empieza.']}
    s, ind, be, cmp = m['statement'], m['indicators'], m['break_even'], m['comparisons']
    no_exp = not m['has_expenses']
    rows = []
    for key, label, formula, est, _ in STATEMENT:
        missing = no_exp and key in NEEDS_EXPENSES
        pct = None if key in ('ventas', 'precio_lista') or missing else m['pct_of_sales'].get(key)
        if key == 'descuentos':
            pct = ind['descuentos_pct']
        rows.append([label + (EST if est else ''), 'Sin gastos' if missing else s[key], pct, formula])
    p, ly = cmp['previous_month'], cmp['last_year']

    def c(x):
        return (x or {}).get('value'), (x or {}).get('change_pct')
    ind_rows = [
        ['Ventas', s['ventas'], *c(p['ventas']), *c(ly['ventas'])],
        ['Transacciones', ind['transacciones'], *c(p['transacciones']), *c(ly['transacciones'])],
        ['Ticket promedio', ind['ticket'], *c(p['ticket']), *c(ly['ticket'])],
        ['Unidades', ind['unidades'], *c(p['unidades']), None, None],
    ]
    ratios = [
        ['Prendas por factura', ind['prendas_por_factura'], NUM],
        ['Descuentos ÷ precio de lista', ind['descuentos_pct'], PCT],
        ['Gastos ÷ ventas', ind['gastos_ventas_pct'], PCT],
        ['Nómina ÷ ventas', ind['nomina_ventas_pct'], PCT],
    ]
    sections = [
        section('Estado de resultados', ['Concepto', 'Valor', '% de ventas', 'Fórmula'], [TEXT, MONEY, PCT, TEXT], rows),
        section('Punto de equilibrio' + EST, ['Concepto', 'Valor', 'Fórmula'], [TEXT, MONEY, TEXT], [
            ['Gastos fijos del mes', be['fixed_costs'], 'Gastos fijos que restan utilidad (si se pagó más, lo pagado)'],
            ['Margen de contribución', as_text(be['contribution_pct'], PCT), '(Ventas − costo − fletes − comisiones) ÷ ventas'],
            ['Punto de equilibrio del mes', be['month'], 'Gastos fijos ÷ margen de contribución'],
            ['Punto de equilibrio al día', be['day'], f'Del mes ÷ {m["days_in_month"]} días'],
            ['Con las cuotas de crédito', be['month_with_cuotas'], '(Gastos fijos + cuotas) ÷ margen de contribución'],
            ['Avance', as_text(be['progress_pct'], PCT), 'Ventas ÷ punto de equilibrio'],
            ['Ritmo al cierre del mes', be['pace_month'], 'Ventas a hoy ÷ días corridos × días del mes (mes en curso)'],
        ]),
        {**section('Indicadores y comparaciones', ['Indicador', 'Este mes', 'Mes anterior', 'Cambio', 'Mismo mes año pasado', 'Cambio'],
                   [TEXT, MONEY, MONEY, PCT, MONEY, PCT], ind_rows),
         'row_formats': [[TEXT, k, k, PCT, k, PCT] for k in (MONEY, NUM, MONEY, NUM)]},
        section('Otros indicadores', ['Indicador', 'Valor'], [TEXT, TEXT], [[r[0], as_text(r[1], r[2])] for r in ratios]),
        section('Salidas del mes por clase', ['Clase', 'Total', 'Baja la utilidad', 'Baja lo que quedó'],
                [TEXT, MONEY, TEXT, TEXT],
                [[o['label'], o['total'], o['reduces_utility'], o['reduces_what_is_left']] for o in m['outflows']]),
        section('Detalle de las salidas', ['Fecha', 'Clase', 'Concepto', 'Categoría', 'Valor', 'Interés'],
                [DATE, TEXT, TEXT, TEXT, MONEY, MONEY],
                [[_d(i['date']), o['label'], i['concept'], _category(i.get('subcategory') or i['category']), i['amount'], i['interest'] or None]
                 for o in m['outflows'] for i in o['items']], own_sheet=True),
    ]
    rng = f"Mes anterior: {_d(p['range'][0])} a {_d(p['range'][1])}; año pasado: {_d(ly['range'][0])} a {_d(ly['range'][1])}."
    return {'title': title, 'subtitle': sub + (f" · datos hasta el {_d(m['data_until'])}" if m.get('data_until') else ''),
            'sections': sections, 'notes': m['warnings'] + [rng, f'Margen KOAJ: {m["margin_pct"]} %.', NOTE_ESTIMADO, NOTE_REGISTRADO]}


YEAR_ROWS = [
    ('ventas', 'Ventas netas', MONEY, False), ('ventas_vs_anio_anterior', 'vs. mismo mes del año pasado', PCT, False),
    ('precio_lista', 'Precio de lista vendido', MONEY, False), ('descuentos', 'Descuentos', MONEY, False),
    ('costo_estimado', 'Costo de la ropa', MONEY, True), ('fletes', 'Fletes y moto carro', MONEY, False),
    ('utilidad_bruta', 'Utilidad bruta', MONEY, True), ('margen_bruto_pct', 'Margen bruto', PCT, True),
    ('gastos_operativos', 'Gastos operativos', MONEY, False), ('gastos_financieros', 'Gastos financieros', MONEY, False),
    ('utilidad_neta', 'Utilidad neta', MONEY, True), ('margen_neto_pct', 'Margen neto', PCT, True),
    ('cuotas', 'Cuotas de crédito (capital)', MONEY, False), ('recompras', 'Recompras enviadas', MONEY, False),
    ('lo_que_quedo', 'Lo que quedó', MONEY, False), ('transacciones', 'Transacciones', NUM, False),
    ('ticket', 'Ticket promedio', MONEY, False), ('unidades', 'Unidades', NUM, False),
    ('inventario', 'Inventario fin de mes', MONEY, False), ('inventario_costo', 'Inventario a costo', MONEY, True),
    ('inventario_cambio', 'Cambio del inventario', MONEY, False),
    ('inventario_cambio_sin_ajuste', 'Cambio sin el ajuste de 2025', MONEY, False),
]
YEAR_EXPENSE_KEYS = ('gastos_operativos', 'gastos_financieros', 'utilidad_neta', 'margen_neto_pct', 'fletes', 'cuotas')


def year_report(y: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    months = [m for m in y['months'] if m.get('has_data')]
    cols = ['Concepto'] + [m['label'] + (' (en curso)' if m.get('in_progress') else '') for m in months] + ['Total', 'Promedio']
    rows, fmts = [], []
    has_sin_ajuste = any(m.get('inventario_cambio_sin_ajuste') is not None for m in months)
    for key, label, kind, est in YEAR_ROWS:
        if key == 'inventario_cambio_sin_ajuste' and not has_sin_ajuste:
            continue
        cells = []
        for m in months:
            if key in YEAR_EXPENSE_KEYS and not m.get('has_expenses'):
                cells.append('sin gastos')
            else:
                cells.append(m.get(key))
        rows.append([label + (EST if est else '')] + cells + [y['totals'].get(key), y['averages'].get(key)])
    fmt_row = [TEXT] + [MONEY] * (len(cols) - 1)
    # Formato por fila: el reporte lleva el formato de cada fila en la primera celda (ver row_formats)
    fmts = [kind for key, _, kind, _ in YEAR_ROWS if not (key == 'inventario_cambio_sin_ajuste' and not has_sin_ajuste)]
    sec = section(f'Mes a mes {y["year"]}', cols, fmt_row, rows)
    sec['row_formats'] = fmts
    best, worst = y.get('best_month'), y.get('worst_month')
    extra = []
    if best:
        extra.append(f"Mejor mes en ventas: {best['label']} ({cop(best['ventas'])})"
                     + (f"; más flojo: {worst['label']} ({cop(worst['ventas'])})" if worst else '') + '.')
    return {'title': f'Radiografía del año · {store_name}', 'subtitle': str(y['year']),
            'sections': [sec] if months else [],
            'notes': (y['warnings'] + extra + ['Promedio: solo los meses cerrados.', f'Margen KOAJ: {y["margin_pct"]} %.',
                                               NOTE_ESTIMADO, NOTE_REGISTRADO]) if months else ['Todavía no hay ventas cargadas de ese año.']}


def inventory_report(inv: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    t = inv['totals']
    snap = inv.get('alegra_snapshot')
    summary = [
        ['Inventario a precio de venta', t['valor_venta'], 'Stock de hoy en Alegra × precio de lista'],
        ['Inventario a costo' + EST, t['valor_costo'], f'× (1 − {inv["margin_pct"]} %)'],
        ['Prendas en stock', as_text(t['unidades'], NUM), f'{t["referencias"]} referencias'],
        ['Reporte de valor de Alegra', snap['value'] if snap else None, f'Al {_d(snap["as_of"])}' if snap else ''],
        ['Días de inventario', as_text(t['dias_inventario'], NUM), 'Inventario ÷ lo que se vende al día a precio de lista'],
        ['Vendido al día (precio de lista)', t['vendido_lista_dia'], f'Últimos {inv["sales_window"]["loaded_days"]} días'],
        ['Rotación al año' + EST, as_text(t['rotacion_anual'], NUM) + (' veces' if t['rotacion_anual'] else ''),
         f'Lo vendido en {t["rotation_days_used"]} días llevado a 12 meses ÷ inventario de hoy'],
        ['Plata parada' + EST, t['plata_parada'],
         f'{t["quiet_count"]} referencias, {t["quiet_units"]} prendas sin venta ni llegada en {inv["quiet_days"]} días '
         f'({as_text(t["plata_parada_pct"], PCT)} del inventario a costo)'],
    ]
    cols = ['Prenda', 'Vendidas', 'Ventas', 'Descuento', 'Utilidad' + EST, 'Stock', 'Valor a costo' + EST,
            'Días de inventario', 'Plata parada' + EST]
    fm = [TEXT, NUM, MONEY, PCT, MONEY, NUM, MONEY, NUM, MONEY]

    def type_rows(rows):
        return [[r['name'], r['units'], r['ventas'], r['descuento_pct'], r['utilidad_estimada'], r['stock'], r['valor_costo'],
                 (r['dias_inventario'] if r['dias_inventario'] is not None else 'sin ventas') if r['stock'] > 0 else 'agotado',
                 r['plata_parada'] or None] for r in rows]
    quiet = [[q['name'], q['stock'], q['price'], q['plata_parada'],
              _d(q['last_sale']) if q['last_sale'] else 'sin ventas en 2026',
              _d(q['last_arrival']) if q['last_arrival'] else 'sin registro'] for q in inv['quiet']]
    return {
        'title': f'Radiografía del inventario · {store_name}', 'subtitle': f'Hoy · quieta = {inv["quiet_days"]} días',
        'sections': [
            section('Resumen', ['Concepto', 'Valor', 'Cómo sale'], [TEXT, MONEY, TEXT], summary),
            section('Las que más rotan', ['Prenda', 'Días de inventario', 'Stock'], [TEXT, NUM, NUM],
                    [[r['name'], r['dias_inventario'], r['stock']] for r in inv['fastest']]),
            section('Las que menos rotan', ['Prenda', 'Días de inventario', 'Stock'], [TEXT, NUM, NUM],
                    [[r['name'], r['dias_inventario'] if r['dias_inventario'] is not None else 'sin ventas', r['stock']]
                     for r in inv['slowest']]),
            section('Por departamento', cols, fm, type_rows(inv['by_department'])),
            section('Por tipo de prenda', cols, fm, type_rows(inv['by_type']), own_sheet=True),
            section(f'Prendas quietas ({t["quiet_count"]})',
                    ['Prenda (talla)', 'Stock', 'Precio', 'Plata parada' + EST, 'Última venta', 'Última llegada'],
                    [TEXT, NUM, MONEY, MONEY, TEXT, TEXT], quiet, own_sheet=True),
        ],
        'notes': inv['warnings'] + (['Se muestran las 300 con más plata parada.'] if inv.get('quiet_truncated') else [])
        + ['Con un margen igual para todo, la utilidad por prenda solo cambia por los descuentos.', NOTE_ESTIMADO],
    }


MEDIO = {'ahorro': 'Datáfono débito', 'credito': 'Datáfono crédito', 'addi': 'Addi', 'bold': 'Bold'}


def cash_flow_report(cf: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    t, w = cf['today'], cf['today']['withdraw']
    retiro = [[a['name'] + (f" ({a['note'].lower()})" if a.get('note') else ''), a['available']] for a in t['accounts']]
    retiro.append(['Plata en las cuentas hoy', w['plata_hoy']])
    avisos = []
    for a in w['avisos']:
        free = a['value'] < 1 and a.get('items')
        avisos.append([a['label'] + (EST if a.get('estimated') else ''), 'sin valor fijo' if free else a['value']])
        for i in a.get('items') or []:
            if a['key'] == 'fijos':
                avisos.append([f"    {i['name']} (día {i['due_day']})", i['value']])
            elif a['key'] == 'cuotas':
                avisos.append([f"    {i['group']} · {i['name']}", i['value'] or 'cuota libre'])
    avisos.append(['Quedarían si se pagara todo (VALOR APROXIMADO)', w['quedarian']])

    def debts(rows):
        out = []
        for x in rows:
            if x['value'] < 1:
                continue
            out.append([x['label'], x['value']])
            for i in x.get('items') or []:
                out.append([f"    Llega el {_d(i['date'])} · {MEDIO.get(i['medio'], i['medio'])}" if i.get('date')
                            else f"    {i['name']}", i.get('value', i.get('balance'))])
        return out
    sections = [
        section(f'¿Cuánto se puede retirar hoy?{EST} (al {_d(t["date"])})', ['Cuenta', 'Plata'], [TEXT, MONEY], retiro),
        section('Avisos: lo que falta pagar este mes (no se resta solo)', ['Aviso', 'Valor'], [TEXT, MONEY], avisos),
        section('Lo que le deben a la tienda', ['Concepto', 'Valor'], [TEXT, MONEY],
                debts(t['receivable']) + [['Total', t['receivable_total']]]),
        section('Lo que debe la tienda', ['Concepto', 'Valor'], [TEXT, MONEY],
                debts(t['payable']) + [['Total', t['payable_total']]]),
    ]
    notes = [w['formula']]
    if w.get('retiros_mes'):
        notes.append(f"Ganancias de socios ya sacadas este mes: {cop(w['retiros_mes'])}.")
    if not cf.get('future'):
        f = cf['flow']
        ins = [[e['label'], e['total']] for e in f['entradas']] + [['Total', f['entradas_total']]]
        if f['ajustes']:
            ins.append(['Ajustes a mano (igualar al banco)', f['ajustes']])
        if f['traslados']['bruto']:
            ins.append(['Traslados entre cuentas propias (no cuentan)', f['traslados']['bruto']])
        sections += [
            section(f'La plata del mes: {cf["label"]}', ['Concepto', 'Valor'], [TEXT, MONEY], [
                ['Saldo al empezar', f['initial']], ['Entró', f['entradas_total']], ['Salió', f['salidas_total']],
                ['Saldo hoy' if cf['in_progress'] else 'Saldo al terminar', f['final']], ['Cambio en el mes', f['change']]]),
            section('Lo que entró', ['Concepto', 'Valor'], [TEXT, MONEY], ins),
            section('Lo que salió', ['Clase', 'Total', 'Baja la utilidad'], [TEXT, MONEY, TEXT],
                    [[s['label'], s['total'], s['reduces_utility']] for s in f['salidas']] + [['Total', f['salidas_total'], '']]),
            section('Detalle de lo que salió', ['Fecha', 'Clase', 'Concepto', 'Valor'], [DATE, TEXT, TEXT, MONEY],
                    [[_d(i['date']), s['label'], i['concept'] + (' (caja del día)' if i.get('caja') else ''), i['amount']]
                     for s in f['salidas'] for i in s['items']], own_sheet=True),
            section('Por cuenta', ['Cuenta', 'Al empezar', 'Hoy' if cf['in_progress'] else 'Al terminar', 'Cambio'],
                    [TEXT, MONEY, MONEY, MONEY], [[a['name'], a['initial'], a['final'], a['change']] for a in f['accounts']]),
        ]
        b = cf.get('bridge')
        if b:
            sections.append(section('Utilidad contra plata', ['Concepto', 'Valor'], [TEXT, MONEY],
                                    [['Utilidad neta' + EST, b['utilidad_neta']]] + [[l['label'], l['value']] for l in b['lines']]
                                    + [['= Cambio en la plata de las cuentas', b['cambio_plata']]]))
        notes = cf['warnings'] + notes
    return {'title': f'Flujo de caja · {store_name}', 'subtitle': cf['label'].capitalize(), 'sections': sections,
            'notes': notes + [NOTE_REGISTRADO, NOTE_ESTIMADO]}


COMPARE_ROWS = [
    ('Resultado del mes', [
        ('Ventas netas', ('statement', 'ventas'), MONEY, False), ('Costo estimado de lo vendido' + EST, ('statement', 'costo_estimado'), MONEY, False),
        ('Fletes', ('statement', 'fletes'), MONEY, False), ('Utilidad bruta' + EST, ('statement', 'utilidad_bruta'), MONEY, False),
        ('Margen bruto' + EST, ('pct', 'utilidad_bruta'), PCT, False),
        ('Gastos operativos', ('statement', 'gastos_operativos'), MONEY, True),
        ('Gastos financieros', ('statement', 'gastos_financieros'), MONEY, True),
        ('Utilidad neta' + EST, ('statement', 'utilidad_neta'), MONEY, True), ('Margen neto' + EST, ('pct', 'utilidad_neta'), PCT, True),
        ('Cuotas de crédito (capital)', ('statement', 'cuotas'), MONEY, True), ('Recompras', ('statement', 'recompras'), MONEY, False),
        ('Lo que quedó', ('statement', 'lo_que_quedo'), MONEY, True)]),
    ('Indicadores', [
        ('Transacciones', ('indicators', 'transacciones'), NUM, False), ('Ticket promedio', ('indicators', 'ticket'), MONEY, False),
        ('Prendas vendidas', ('indicators', 'unidades'), NUM, False), ('Descuentos', ('indicators', 'descuentos_pct'), PCT, False),
        ('Gastos ÷ ventas', ('indicators', 'gastos_ventas_pct'), PCT, True), ('Nómina ÷ ventas', ('indicators', 'nomina_ventas_pct'), PCT, True),
        ('Punto de equilibrio del mes' + EST, ('break_even', 'month'), MONEY, False),
        ('Avance contra el punto de equilibrio' + EST, ('break_even', 'progress_pct'), PCT, False)]),
    ('La plata del mes (cuentas)', [
        ('Saldo al empezar', ('flow', 'initial'), MONEY, False), ('Entró', ('flow', 'entradas_total'), MONEY, False),
        ('Salió', ('flow', 'salidas_total'), MONEY, False), ('Saldo al terminar / hoy', ('flow', 'final'), MONEY, False)]),
    ('Hoy', [
        ('Plata en las cuentas', ('today', 'plata'), MONEY, False),
        ('Lo que le deben (sin la otra tienda)', ('today', 'receivable_total'), MONEY, False),
        ('Lo que debe (sin la otra tienda)', ('today', 'payable_total'), MONEY, False),
        ('Avisos del mes (no se restan solos)' + EST, ('today', 'avisos_total'), MONEY, False),
        ('Quedarían si se pagara todo' + EST, ('today', 'quedarian'), MONEY, False)]),
    ('Inventario (foto de Alegra del mes)', [
        ('A precio de venta', ('inventory', 'valor_venta'), MONEY, False), ('A costo' + EST, ('inventory', 'valor_costo'), MONEY, False)]),
]


def store_today(t: Dict[str, Any]) -> Dict[str, Any]:
    """Lo de hoy de una tienda sin la deuda entre tiendas (como "Las dos")."""
    avisos = sum(a['value'] for a in t['withdraw']['avisos'] if a['key'] != 'otra_tienda')
    return {'plata': t['plata'], 'avisos_total': avisos, 'quedarian': t['plata'] - avisos,
            'receivable_total': sum(x['value'] for x in t['receivable'] if x['key'] != 'otra_tienda'),
            'payable_total': sum(x['value'] for x in t['payable'] if x['key'] != 'otra_tienda')}


def compare_report(c: Dict[str, Any]) -> Dict[str, Any]:
    cols = [{**s, 'today': store_today(s['today'])} for s in c['stores']] + [c['consolidated']]
    sections = []
    for title, rows in COMPARE_ROWS:
        out, fmts = [], []
        for label, (a, b), kind, needs in rows:
            cells = []
            for col in cols:
                if col.get('future') and a not in ('today', 'inventory'):
                    cells.append(None)
                elif needs and not col.get('has_expenses'):
                    cells.append('sin gastos')
                else:
                    cells.append((col.get(a) or {}).get(b))
            out.append([label] + cells)
            fmts.append(kind)
        sec = section(title, ['Concepto'] + [col['name'].replace('KOAJ ', '') for col in cols],
                      [TEXT] + [MONEY] * len(cols), out)
        sec['row_formats'] = fmts
        sections.append(sec)
    debt = c['consolidated']['today'].get('inter_store_debt')
    notes = ([f'Préstamo entre las tiendas hoy: {cop(debt)}. No aparece en "Las dos" ni en lo que le deben o debe cada una.']
             if debt else []) + [n for n in c['notes'] if not (debt and 'préstamo' in n)]
    warns = sorted({f"{s['name']}: {w}" for s in c['stores'] for w in (s.get('warnings') or []) if 'caja del día' not in w})
    return {'title': 'Comparativo de las tiendas', 'subtitle': c['label'].capitalize(), 'sections': sections,
            'notes': warns + notes + [NOTE_ESTIMADO]}


# ─────────────────────────────────────────────
#  Reporte → Excel / PDF
# ─────────────────────────────────────────────

XLSX_FORMATS = {MONEY: '"$" #,##0;-"$" #,##0', PCT: '0.0%', NUM: '#,##0.#'}


def _cell_format(sec: Dict[str, Any], r: int, c: int) -> str:
    """Formato de una celda: por columna, o por fila si la sección trae
    row_formats (un formato para toda la fila o una lista por columna)."""
    if c > 0 and sec.get('row_formats'):
        rf = sec['row_formats'][r]
        return rf[c] if isinstance(rf, list) else rf
    return sec['formats'][c]


def _category(slug: Optional[str]) -> str:
    return (slug or '').replace('_', ' ').capitalize()


def to_xlsx(report: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Radiografía'
    head_fill = PatternFill('solid', fgColor='E5E7EB')
    widths: Dict[Any, Dict[int, int]] = {}

    def write(sheet, sec, row):
        sheet.cell(row=row, column=1, value=sec['title']).font = Font(bold=True, size=12)
        row += 1
        for ci, name in enumerate(sec['columns'], start=1):
            cell = sheet.cell(row=row, column=ci, value=name)
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        row += 1
        for ri, values in enumerate(sec['rows']):
            for ci, v in enumerate(values):
                kind = _cell_format(sec, ri, ci)
                if isinstance(v, bool):
                    v = 'Sí' if v else 'No'
                cell = sheet.cell(row=row, column=ci + 1, value='—' if v is None else v)
                if isinstance(v, (int, float)) and kind in XLSX_FORMATS:
                    cell.number_format = XLSX_FORMATS[kind]
                if ci == 0 and isinstance(v, str) and (v.startswith('Total') or v.startswith('=') or v.startswith('Quedarían')):
                    cell.font = Font(bold=True)
                w = widths.setdefault(sheet.title, {})
                w[ci + 1] = max(w.get(ci + 1, 10), min(len(as_text(v, kind)) + 2, 70))
            row += 1
        return row + 1

    ws.cell(row=1, column=1, value=report['title']).font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=report['subtitle'])
    ws.cell(row=3, column=1, value=f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")} · mismas cifras de la pantalla')
    row = 5
    for sec in report['sections']:
        if sec['own_sheet'] and sec['rows']:
            sheet = wb.create_sheet(sec['title'][:31].replace('/', '-').replace(':', ''))
            write(sheet, sec, 1)
            sheet.freeze_panes = 'B3'
            ws.cell(row=row, column=1, value=f'{sec["title"]}: ver la hoja "{sheet.title}" ({len(sec["rows"])} filas).')
            row += 2
        else:
            row = write(ws, sec, row)
    notes = wb.create_sheet('Notas')
    notes.cell(row=1, column=1, value='Notas, fórmulas y avisos').font = Font(bold=True, size=12)
    for i, n in enumerate(report['notes'], start=2):
        notes.cell(row=i, column=1, value=n).alignment = Alignment(wrap_text=True, vertical='top')
    notes.column_dimensions['A'].width = 120
    for sheet in wb.worksheets:
        for col, width in widths.get(sheet.title, {}).items():
            sheet.column_dimensions[get_column_letter(col)].width = width
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(report: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=7.5, leading=9)
    small_r = ParagraphStyle('small_r', parent=small, alignment=2)
    head = ParagraphStyle('head', parent=small, fontName='Helvetica-Bold')
    head_r = ParagraphStyle('head_r', parent=head, alignment=2)
    h3 = ParagraphStyle('h3', parent=styles['Heading3'], keepWithNext=1)   # el título no queda solo al final de la hoja
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(letter), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm, title=report['title'])
    width = landscape(letter)[0] - 2.4 * cm
    story = [Paragraph(report['title'], styles['Title']), Paragraph(report['subtitle'], styles['Normal']),
             Paragraph(f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")} · mismas cifras de la pantalla', small),
             Spacer(1, 8)]

    def esc(s: str) -> str:
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    for sec in report['sections']:
        story.append(Paragraph(esc(sec['title']), h3))
        if not sec['rows']:
            story.append(Paragraph('Nada.', small))
            continue
        n = len(sec['columns'])
        data = [[Paragraph(esc(c), head if ci == 0 or sec['formats'][ci] in (TEXT, DATE) else head_r)
                 for ci, c in enumerate(sec['columns'])]]
        for ri, values in enumerate(sec['rows']):
            data.append([Paragraph(esc(as_text(v, _cell_format(sec, ri, ci))),
                                   small if ci == 0 or _cell_format(sec, ri, ci) in (TEXT, DATE) else small_r)
                         for ci, v in enumerate(values)])
        first = min(0.38, max(0.22, 1.6 / n)) * width if n > 2 else 0.6 * width
        rest = (width - first) / (n - 1) if n > 1 else width
        table = LongTable(data, colWidths=[first] + [rest] * (n - 1), repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E5E7EB')),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story += [table, Spacer(1, 8)]
    story.append(Paragraph('Notas, fórmulas y avisos', styles['Heading3']))
    for note in report['notes']:
        story.append(Paragraph('• ' + esc(note), small))
    doc.build(story)
    return out.getvalue()


MIMES = {'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'pdf': 'application/pdf'}


def render(report: Dict[str, Any], fmt: str) -> bytes:
    return to_xlsx(report) if fmt == 'xlsx' else to_pdf(report)


def filename(view: str, store: Optional[str], period: str, fmt: str) -> str:
    return f"radiografia_{view}{'_' + store if store else ''}_{period}.{fmt}"
