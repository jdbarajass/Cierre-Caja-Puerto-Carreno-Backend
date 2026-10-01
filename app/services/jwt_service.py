"""
Servicio para manejo de JWT tokens
"""
import jwt
from datetime import datetime, timedelta
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class JWTService:
    """Servicio para generar y validar tokens JWT"""

    @staticmethod
    def generate_token(user_id: int, email: str, role: str, store_code: str = None) -> str:
        """
        Genera un token JWT para el usuario

        Args:
            user_id: ID del usuario
            email: Email del usuario
            role: Rol del usuario
            store_code: Tienda asignada al usuario (multi-tienda, ver app/stores.py)

        Returns:
            Token JWT como string
        """
        try:
            expiration_hours = current_app.config.get('JWT_EXPIRATION_HOURS', 8)
            secret_key = current_app.config.get('JWT_SECRET_KEY')
            algorithm = current_app.config.get('JWT_ALGORITHM', 'HS256')

            payload = {
                'userId': user_id,
                'email': email,
                'role': role,
                'storeCode': store_code,
                'iat': datetime.utcnow(),
                'exp': datetime.utcnow() + timedelta(hours=expiration_hours)
            }

            token = jwt.encode(payload, secret_key, algorithm=algorithm)

            logger.info(f"Token generado para usuario: {email}")
            return token

        except Exception as e:
            logger.error(f"Error generando token: {str(e)}")
            raise

    @staticmethod
    def verify_token(token: str) -> dict:
        """
        Verifica y decodifica un token JWT

        Args:
            token: Token JWT a verificar

        Returns:
            Payload decodificado del token

        Raises:
            jwt.ExpiredSignatureError: Si el token ha expirado
            jwt.InvalidTokenError: Si el token es inválido
        """
        try:
            secret_key = current_app.config.get('JWT_SECRET_KEY')
            algorithm = current_app.config.get('JWT_ALGORITHM', 'HS256')

            payload = jwt.decode(token, secret_key, algorithms=[algorithm])

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expirado")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token inválido: {str(e)}")
            raise

    @staticmethod
    def decode_token_without_verification(token: str) -> dict:
        """
        Decodifica un token sin verificar la firma (para debugging)

        Args:
            token: Token JWT

        Returns:
            Payload del token
        """
        return jwt.decode(token, options={"verify_signature": False})
