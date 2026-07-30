"""
Agrupamiento/normalizacion de nombre_empleada para Control de Empleadas.
Mismo criterio (laxo a proposito) usado en el frontend
(src/utils/employeeGroups.js) para poder agrupar variantes/typos
historicos como "monika vargas".
"""
import unicodedata

CANONICAL_NAMES = {
    'monica': 'Mónica Vargas',
    'rita': 'Rita Infante',
}


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


def canonical_name_for(nombre):
    key = group_key_for(nombre)
    return CANONICAL_NAMES.get(key)
