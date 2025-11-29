"""
Parser de códigos SKU para productos KOAJ

Este módulo parsea códigos SKU y nombres de productos para extraer:
- Género/Departamento (HOMBRE, MUJER, NIÑO, NIÑA)
- Tipo de prenda
- Precio
- Talla

Formato SKU: 10 + GÉNERO(51-54) + CÓDIGO_PRENDA + PRECIO + TALLA
Ejemplo: 1052388990010 = 10 + 52 + 38 + 89900 + 010
"""

import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SKUParser:
    """Parser de códigos SKU y nombres de productos KOAJ"""

    # Mapeo de género por código (dígitos 3-4 del SKU)
    GENDER_MAP = {
        '51': 'HOMBRE',
        '52': 'MUJER',
        '53': 'NIÑO',
        '54': 'NIÑA'
    }

    # Mapeo completo de tipos de prenda (67 códigos)
    GARMENT_TYPE_MAP = {
        # Accesorios
        '55': 'MALETAS', '50': 'GORRAS', '49': 'CINTURONES',
        '48': 'MEDIAS', '47': 'BOXER',
        # Abrigos
        '46': 'CHAQUETAS', '45': 'CHALECOS', '32': 'BUZO CAPOTA', '31': 'FLEECE',
        # Tops (tallas alfabéticas)
        '44': 'POLO', '43': 'CAMISA MANGA LARGA', '27': 'CAMISA MANGA CORTA',
        '40': 'BLUSAS', '34': 'CROP TOP', '1': 'POLO MUJER', '5': 'BLUSA NIÑA',
        # Pantalones (tallas numéricas)
        '38': 'JOGGER MUJER', '16': 'JOGGER HOMBRE', '37': 'PANTALON TELA',
        '13': 'PANTALON TELA NIÑA', '42': 'BERMUDAS', '41': 'SHORT',
        '18': 'PANTALONETA NIÑO', '66': 'SHORT NIÑA', '67': 'PANTALONETA MUJER',
        # Jeans (tallas numéricas)
        '26': 'BOYFRIEND', '25': 'MOMFIT', '24': 'BOTA CAMPANA',
        '23': 'CARGO', '22': '90s', '20': 'JEGGING', '61': 'DRILL HOMBRE',
        # Vestidos/Faldas
        '36': 'VESTIDO', '19': 'VESTIDO NIÑA', '62': 'VESTIDOS TALLA UNICA',
        '29': 'FALDA', '60': 'FALDA NIÑA', '65': 'FALDA TALLA UNICA',
        # Bodys
        '35': 'BODYS', '7': 'BODY NIÑA', '6': 'BODY NIÑO', '28': 'OVEROL',
        # Otros
        '39': 'GAFAS', '33': 'SOMBRERO', '30': 'ZAPATOS', '21': 'SET MEDIAS',
        '14': 'LEGGIN NIÑA', '12': 'BICICLETERO NIÑA',
        '63': 'BLUSAS TALLA UNICA', '64': 'SUETER TEJIDO TALLA UNICA',
        # Niños
        '17': 'POLO NIÑO', '10': 'BUZO NIÑO', '11': 'CAMISA NIÑO', '8': 'BUZO NIÑA',
        # Accesorios KOAJ
        '9': 'TERMOS KOAJ', '4': 'PINES KOAJ', '3': 'BOLSA LICENCIA', '2': 'VASOS KOAJ',
        # Especiales
        '15': 'BONO REGALO'
    }

    # Tallas alfabéticas: XS, S, M, L, XL (para camisetas, polos, blusas, etc.)
    ALPHA_SIZE_MAP = {
        '1': 'XS',
        '2': 'S',
        '3': 'M',
        '4': 'L',
        '5': 'XL'
    }

    # Tallas numéricas: 2, 4, 6, ..., 38 (para jeans, joggers, pantalones)
    NUMERIC_SIZE_MAP = {
        '002': '2', '004': '4', '006': '6', '008': '8',
        '010': '10', '012': '12', '014': '14', '016': '16',
        '018': '18', '020': '20', '022': '22', '024': '24',
        '026': '26', '028': '28', '030': '30', '032': '32',
        '034': '34', '036': '36', '038': '38',
        # También aceptar sin ceros a la izquierda
        '2': '2', '4': '4', '6': '6', '8': '8',
        '10': '10', '12': '12', '14': '14', '16': '16',
        '18': '18', '20': '20', '22': '22', '24': '24',
        '26': '26', '28': '28', '30': '30', '32': '32',
        '34': '34', '36': '36', '38': '38'
    }

    # Tallas para niños (pueden ser rangos)
    KIDS_SIZE_MAP = {
        '1214': '12-14', '1012': '10-12', '0810': '8-10', '0608': '6-8',
        '0406': '4-6', '0204': '2-4'
    }

    # Códigos de productos con talla única
    UNIQUE_SIZE_CODES = ['62', '63', '64', '65']

    @staticmethod
    def extract_size_from_product_name(name: str) -> Dict:
        """
        Estrategia principal: extraer talla del nombre del producto

        Parsea un nombre como "CAMISETA MUJER 39900 / 1052399004"
        y extrae todos los atributos necesarios.

        Args:
            name: Nombre completo del producto de Alegra

        Returns:
            {
                'size': str,           # "L", "10", "ÚNICA", "UNKNOWN"
                'size_code': str,      # "4", "010", etc.
                'sku_code': str,       # "1052399004"
                'gender': str,         # "MUJER", "HOMBRE", "NIÑO", "NIÑA", "UNKNOWN"
                'price': int,          # 39900
                'product_base': str,   # "CAMISETA MUJER"
                'is_valid': bool,
                'error': str           # Si is_valid=False
            }
        """
        try:
            # Dividir por "/"
            parts = name.split('/')
            if len(parts) != 2:
                return {
                    'size': 'UNKNOWN',
                    'size_code': '',
                    'sku_code': '',
                    'gender': 'UNKNOWN',
                    'price': 0,
                    'product_base': name,
                    'is_valid': False,
                    'error': 'Formato de nombre inválido (falta /)'
                }

            # Parte 1: Nombre base y precio
            name_part = parts[0].strip()
            # Parte 2: SKU
            sku_code = parts[1].strip()

            # Extraer género del nombre
            gender = SKUParser.extract_gender_from_name(name_part)

            # Extraer precio del nombre (último número antes del /)
            price_match = re.findall(r'\d+', name_part)
            price = int(price_match[-1]) if price_match else 0

            # Obtener nombre base sin precio
            product_base = re.sub(r'\s+\d+\s*$', '', name_part).strip()

            # Parsear SKU para obtener talla
            sku_result = SKUParser.parse_sku(sku_code, gender, product_base)

            return {
                'size': sku_result['size'],
                'size_code': sku_result['size_code'],
                'sku_code': sku_code,
                'gender': gender if gender != 'UNKNOWN' else sku_result.get('gender', 'UNKNOWN'),
                'price': price,
                'product_base': product_base,
                'is_valid': sku_result['is_valid'],
                'error': sku_result.get('error', '')
            }

        except Exception as e:
            logger.warning(f"Error parseando nombre '{name}': {str(e)}")
            return {
                'size': 'UNKNOWN',
                'size_code': '',
                'sku_code': '',
                'gender': 'UNKNOWN',
                'price': 0,
                'product_base': name,
                'is_valid': False,
                'error': f'Error de parseo: {str(e)}'
            }

    @staticmethod
    def parse_sku(sku_code: str, gender_hint: str = None, product_name_hint: str = None) -> Dict:
        """
        Parsea un código SKU completo

        Formato: 10 + GÉNERO(51-54) + CÓDIGO_PRENDA + PRECIO + TALLA

        Args:
            sku_code: Código SKU como "1052388990010"
            gender_hint: Género extraído del nombre (opcional)
            product_name_hint: Nombre del producto para contexto (opcional)

        Returns:
            {
                'sku_code': str,
                'gender_code': str,
                'gender': str,
                'garment_code': str,
                'garment_type': str,
                'price': int,
                'size_code': str,
                'size': str,
                'size_type': str,  # "ALPHA", "NUMERIC", "UNIQUE", "KIDS"
                'is_valid': bool,
                'error': str
            }
        """
        try:
            if not sku_code or len(sku_code) < 8:
                return SKUParser._invalid_sku(sku_code, 'SKU demasiado corto')

            # Verificar que empiece con '10'
            if not sku_code.startswith('10'):
                return SKUParser._invalid_sku(sku_code, 'SKU debe empezar con 10')

            # Extraer código de género (posiciones 2-3, índices [2:4])
            gender_code = sku_code[2:4]
            gender = SKUParser.GENDER_MAP.get(gender_code, gender_hint or 'UNKNOWN')

            # Estrategia: los últimos 1-4 dígitos son la talla
            # Intentar identificar el código de prenda y la talla

            # Caso especial: productos con talla única (códigos 62, 63, 64, 65)
            if any(code in sku_code for code in ['62', '63', '64', '65']):
                return SKUParser._parse_unique_size_sku(sku_code, gender_code, gender)

            # Intentar parseo normal
            # El SKU tiene formato variable, intentaremos múltiples estrategias

            # Estrategia 1: Talla de 1 dígito (alfabéticas: 1-5)
            last_1 = sku_code[-1]
            if last_1 in SKUParser.ALPHA_SIZE_MAP:
                return SKUParser._parse_with_alpha_size(sku_code, gender_code, gender, last_1)

            # Estrategia 2: Talla de 3 dígitos (numéricas: 002-038)
            if len(sku_code) >= 3:
                last_3 = sku_code[-3:]
                if last_3 in SKUParser.NUMERIC_SIZE_MAP:
                    return SKUParser._parse_with_numeric_size(sku_code, gender_code, gender, last_3)

            # Estrategia 3: Talla de 2 dígitos (numéricas sin cero: 10-38)
            if len(sku_code) >= 2:
                last_2 = sku_code[-2:]
                if last_2 in SKUParser.NUMERIC_SIZE_MAP and last_2.isdigit():
                    return SKUParser._parse_with_numeric_size(sku_code, gender_code, gender, last_2)

            # Estrategia 4: Talla de 4 dígitos (niños con rangos: 1214)
            if len(sku_code) >= 4:
                last_4 = sku_code[-4:]
                if last_4 in SKUParser.KIDS_SIZE_MAP:
                    return SKUParser._parse_with_kids_size(sku_code, gender_code, gender, last_4)

            # Si no se pudo determinar, marcar como UNKNOWN
            logger.warning(f"No se pudo determinar talla para SKU: {sku_code}")
            return {
                'sku_code': sku_code,
                'gender_code': gender_code,
                'gender': gender,
                'garment_code': '',
                'garment_type': 'UNKNOWN',
                'price': 0,
                'size_code': '',
                'size': 'UNKNOWN',
                'size_type': 'UNKNOWN',
                'is_valid': True,  # Es válido pero sin talla identificada
                'error': 'Talla no identificada'
            }

        except Exception as e:
            logger.error(f"Error parseando SKU '{sku_code}': {str(e)}")
            return SKUParser._invalid_sku(sku_code, f'Error: {str(e)}')

    @staticmethod
    def _parse_with_alpha_size(sku_code: str, gender_code: str, gender: str, size_code: str) -> Dict:
        """Parsea SKU con talla alfabética (1-5)"""
        size = SKUParser.ALPHA_SIZE_MAP[size_code]

        # Resto del SKU sin prefijo (10) y género
        middle = sku_code[4:-1]  # Sin '10' + género + última talla

        # Intentar extraer precio (últimos 5 dígitos antes de talla)
        if len(middle) >= 5:
            price_str = middle[-5:]
            if price_str.isdigit():
                price = int(price_str)
                garment_part = middle[:-5]
            else:
                price = 0
                garment_part = middle
        else:
            price = 0
            garment_part = middle

        garment_code = garment_part if garment_part else ''
        garment_type = SKUParser.GARMENT_TYPE_MAP.get(garment_code, 'UNKNOWN')

        return {
            'sku_code': sku_code,
            'gender_code': gender_code,
            'gender': gender,
            'garment_code': garment_code,
            'garment_type': garment_type,
            'price': price,
            'size_code': size_code,
            'size': size,
            'size_type': 'ALPHA',
            'is_valid': True,
            'error': ''
        }

    @staticmethod
    def _parse_with_numeric_size(sku_code: str, gender_code: str, gender: str, size_code: str) -> Dict:
        """Parsea SKU con talla numérica (002-038 o 10-38)"""
        size = SKUParser.NUMERIC_SIZE_MAP[size_code]
        size_len = len(size_code)

        # Resto del SKU sin prefijo (10), género y talla
        middle = sku_code[4:-size_len]

        # Intentar extraer precio (últimos 5 dígitos antes de talla)
        if len(middle) >= 5:
            price_str = middle[-5:]
            if price_str.isdigit():
                price = int(price_str)
                garment_part = middle[:-5]
            else:
                price = 0
                garment_part = middle
        else:
            price = 0
            garment_part = middle

        garment_code = garment_part if garment_part else ''
        garment_type = SKUParser.GARMENT_TYPE_MAP.get(garment_code, 'UNKNOWN')

        return {
            'sku_code': sku_code,
            'gender_code': gender_code,
            'gender': gender,
            'garment_code': garment_code,
            'garment_type': garment_type,
            'price': price,
            'size_code': size_code,
            'size': size,
            'size_type': 'NUMERIC',
            'is_valid': True,
            'error': ''
        }

    @staticmethod
    def _parse_with_kids_size(sku_code: str, gender_code: str, gender: str, size_code: str) -> Dict:
        """Parsea SKU con talla de niños (rangos como 1214)"""
        size = SKUParser.KIDS_SIZE_MAP[size_code]

        # Resto del SKU sin prefijo (10), género y talla
        middle = sku_code[4:-4]

        # Intentar extraer precio (últimos 5 dígitos antes de talla)
        if len(middle) >= 5:
            price_str = middle[-5:]
            if price_str.isdigit():
                price = int(price_str)
                garment_part = middle[:-5]
            else:
                price = 0
                garment_part = middle
        else:
            price = 0
            garment_part = middle

        garment_code = garment_part if garment_part else ''
        garment_type = SKUParser.GARMENT_TYPE_MAP.get(garment_code, 'UNKNOWN')

        return {
            'sku_code': sku_code,
            'gender_code': gender_code,
            'gender': gender,
            'garment_code': garment_code,
            'garment_type': garment_type,
            'price': price,
            'size_code': size_code,
            'size': size,
            'size_type': 'KIDS',
            'is_valid': True,
            'error': ''
        }

    @staticmethod
    def _parse_unique_size_sku(sku_code: str, gender_code: str, gender: str) -> Dict:
        """Parsea SKU con talla única (códigos 62, 63, 64, 65)"""
        # Buscar el código de talla única
        garment_code = ''
        for code in SKUParser.UNIQUE_SIZE_CODES:
            if code in sku_code:
                garment_code = code
                break

        garment_type = SKUParser.GARMENT_TYPE_MAP.get(garment_code, 'TALLA UNICA')

        return {
            'sku_code': sku_code,
            'gender_code': gender_code,
            'gender': gender,
            'garment_code': garment_code,
            'garment_type': garment_type,
            'price': 0,
            'size_code': 'U',
            'size': 'ÚNICA',
            'size_type': 'UNIQUE',
            'is_valid': True,
            'error': ''
        }

    @staticmethod
    def _invalid_sku(sku_code: str, error: str) -> Dict:
        """Retorna estructura para SKU inválido"""
        return {
            'sku_code': sku_code,
            'gender_code': '',
            'gender': 'UNKNOWN',
            'garment_code': '',
            'garment_type': 'UNKNOWN',
            'price': 0,
            'size_code': '',
            'size': 'UNKNOWN',
            'size_type': 'UNKNOWN',
            'is_valid': False,
            'error': error
        }

    @staticmethod
    def extract_gender_from_name(name: str) -> str:
        """
        Extrae género del nombre del producto

        Args:
            name: "CAMISETA MUJER 39900" o "JOGGER HOMBRE"

        Returns:
            "MUJER" | "HOMBRE" | "NIÑO" | "NIÑA" | "UNKNOWN"
        """
        name_upper = name.upper()

        # Orden importa: NIÑA debe ir antes que NIÑO
        if 'NIÑA' in name_upper:
            return 'NIÑA'
        elif 'NIÑO' in name_upper:
            return 'NIÑO'
        elif 'MUJER' in name_upper or 'DAMA' in name_upper:
            return 'MUJER'
        elif 'HOMBRE' in name_upper or 'CABALLERO' in name_upper:
            return 'HOMBRE'

        return 'UNKNOWN'

    @staticmethod
    def determine_size_type(garment_code: str, gender: str) -> str:
        """
        Determina si la prenda usa tallas alfabéticas o numéricas

        Args:
            garment_code: Código de prenda (ej: "38", "25")
            gender: Género del producto

        Returns:
            "ALPHA" | "NUMERIC" | "UNIQUE" | "KIDS"
        """
        # Tallas únicas
        if garment_code in SKUParser.UNIQUE_SIZE_CODES:
            return 'UNIQUE'

        # Jeans y pantalones = numéricas
        jean_codes = ['26', '25', '24', '23', '22', '20', '61']
        pantalon_codes = ['37', '13', '38', '16', '42', '41', '18', '66', '67']

        if garment_code in jean_codes or garment_code in pantalon_codes:
            return 'NUMERIC'

        # Niños pueden tener rangos
        if gender in ['NIÑO', 'NIÑA']:
            return 'KIDS'

        # Por defecto alfabéticas (camisetas, polos, blusas)
        return 'ALPHA'
