"""
Credenciales para los scripts de prueba manual (nunca escritas en el código).

Se leen de variables de entorno y, si faltan, se piden por consola:
  KOAJ_API_URL        (por defecto http://localhost:5000)
  KOAJ_TEST_EMAIL
  KOAJ_TEST_PASSWORD
"""
import getpass
import os


def api_url():
    return os.getenv('KOAJ_API_URL', 'http://localhost:5000').rstrip('/')


def login_payload():
    email = os.getenv('KOAJ_TEST_EMAIL') or input('Correo de la plataforma: ').strip()
    password = os.getenv('KOAJ_TEST_PASSWORD') or getpass.getpass('Contraseña (no se ve al escribir): ')
    return {'email': email, 'password': password}
