#!/usr/bin/env python
"""
Normaliza el campo nombre_empleada en las 5 tablas de Control de Empleadas,
unificando variantes/typos hacia los nombres canonicos:
  - "Monica Vargas"
  - "Rita Infante"

Por defecto corre en modo DRY RUN (solo muestra que cambiaria, no guarda nada).
Ejecutar en modo real: python scripts/normalize_employee_names.py --apply
"""
import sys
import os
import unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import get_config
from app.models.user import db
from app.models.employee_records import (
    EmployeeClothing, EmployeeLoan, EmployeePermission, EmployeeVacation, EmployeePayment
)

# Mismo criterio (laxo a proposito) usado en el frontend (src/utils/employeeGroups.js)
# para agrupar variantes/typos historicos como "monika vargas".
CANONICAL_NAMES = {
    'monica': 'Mónica Vargas',
    'rita': 'Rita Infante',
}

MODELS = [EmployeeClothing, EmployeeLoan, EmployeePermission, EmployeeVacation, EmployeePayment]


def normalize(s):
    s = (s or '').strip().lower()
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def group_key_for(nombre):
    n = normalize(nombre)
    if 'monic' in n or 'monik' in n:
        return 'monica'
    if 'rita' in n:
        return 'rita'
    return None


def run(dry_run=True):
    config = get_config(os.getenv('FLASK_ENV', 'production'))
    app = create_app(config)

    with app.app_context():
        print("=" * 60)
        print("NORMALIZACION DE NOMBRES DE EMPLEADA")
        print("=" * 60)
        print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        print(f"Modo: {'DRY RUN (sin cambios)' if dry_run else 'EJECUCION REAL (se guardaran cambios)'}")
        print()

        total_updates = 0
        unmatched = set()

        for model in MODELS:
            rows = model.query.all()
            table_updates = 0
            for row in rows:
                key = group_key_for(row.nombre_empleada)
                if key is None:
                    unmatched.add(row.nombre_empleada)
                    continue
                canonical = CANONICAL_NAMES[key]
                if row.nombre_empleada != canonical:
                    print(f"  [{model.__tablename__}] id={row.id} '{row.nombre_empleada}' -> '{canonical}'")
                    if not dry_run:
                        row.nombre_empleada = canonical
                    table_updates += 1
            total_updates += table_updates
            print(f"{model.__tablename__}: {table_updates} registro(s) a actualizar ({len(rows)} en total)")
            print()

        if unmatched:
            print("Nombres que NO coinciden con Monica ni Rita (revisar manualmente, no se tocan):")
            for n in sorted(unmatched):
                print(f"  - {n!r}")
            print()

        if not dry_run:
            db.session.commit()
            print(f"EXITO: {total_updates} registro(s) actualizados y guardados.")
        else:
            print(f"DRY RUN: {total_updates} registro(s) se actualizarian.")
            print("Ejecuta con --apply para guardar los cambios de verdad.")


if __name__ == "__main__":
    apply_changes = '--apply' in sys.argv
    run(dry_run=not apply_changes)
