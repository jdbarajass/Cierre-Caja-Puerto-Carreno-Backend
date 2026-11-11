"""
Login robusto (2026-11-11): el admin koaj.puertocarreno recibía 500 en
/auth/login (el frontend lo muestra como "El servidor no responde"). Un
contador de intentos en NULL o un hash dañado no deben tumbar el login.
"""
import bcrypt

from tests.test_multi_store import app  # noqa: F401  (fixture app)
from app.models.user import db, User


def _user(app, email, password_hash, failed=None):
    with app.app_context():
        u = User(email=email, password_hash=password_hash, name='X', role='admin', is_active=True)
        db.session.add(u)
        db.session.flush()
        u.failed_login_attempts = failed
        db.session.commit()


def _hash(pw):
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def test_contador_null_con_clave_errada_da_401_no_500(app, client):
    _user(app, 'null@test.com', _hash('Correcta.2026*'), failed=None)
    r = client.post('/auth/login', json={'email': 'null@test.com', 'password': 'Errada.2026*'})
    assert r.status_code == 401, r.get_json()
    with app.app_context():
        assert User.query.filter_by(email='null@test.com').first().failed_login_attempts == 1


def test_contador_null_con_clave_correcta_entra(app, client):
    _user(app, 'null2@test.com', _hash('Correcta.2026*'), failed=None)
    r = client.post('/auth/login', json={'email': 'null2@test.com', 'password': 'Correcta.2026*'})
    assert r.status_code == 200, r.get_json()


def test_bloqueo_con_fecha_con_zona_no_revienta():
    """Causa real del 10/11-nov (log de Render): Postgres devuelve locked_until
    con zona horaria y compararlo con utcnow() daba TypeError (500)."""
    from datetime import datetime, timedelta, timezone
    u = User(email='z@test.com', password_hash='x', name='Z')
    u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert u.is_locked() is True
    u.locked_until = datetime.now(timezone.utc) - timedelta(hours=20)
    assert u.is_locked() is False
    u.locked_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).astimezone(timezone(timedelta(hours=-5)))
    assert u.is_locked() is True
    u.locked_until = datetime.utcnow() + timedelta(minutes=10)  # sin zona (SQLite / tests)
    assert u.is_locked() is True


def test_bloqueo_vencido_da_5_intentos_nuevos(app, client):
    from datetime import datetime, timedelta
    _user(app, 'lock@test.com', _hash('Correcta.2026*'), failed=0)
    for _ in range(4):
        assert client.post('/auth/login', json={'email': 'lock@test.com', 'password': 'Errada.2026*'}).status_code == 401
    # 5.º error: bloquea
    assert client.post('/auth/login', json={'email': 'lock@test.com', 'password': 'Errada.2026*'}).status_code == 403
    # Durante el bloqueo, ni la correcta entra
    assert client.post('/auth/login', json={'email': 'lock@test.com', 'password': 'Correcta.2026*'}).status_code == 403
    # Pasan los 15 minutos
    with app.app_context():
        u = User.query.filter_by(email='lock@test.com').first()
        u.locked_until = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    # Un error ya no vuelve a bloquear: es el intento 1/5
    r = client.post('/auth/login', json={'email': 'lock@test.com', 'password': 'Errada.2026*'})
    assert r.status_code == 401 and '(1/5' in r.get_json()['message']
    assert client.post('/auth/login', json={'email': 'lock@test.com', 'password': 'Correcta.2026*'}).status_code == 200


def test_hash_danado_da_401_no_500(app, client):
    _user(app, 'hash@test.com', 'esto-no-es-bcrypt', failed=0)
    r = client.post('/auth/login', json={'email': 'hash@test.com', 'password': 'Correcta.2026*'})
    assert r.status_code == 401, r.get_json()
