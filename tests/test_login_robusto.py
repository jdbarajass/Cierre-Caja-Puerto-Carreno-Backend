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


def test_hash_danado_da_401_no_500(app, client):
    _user(app, 'hash@test.com', 'esto-no-es-bcrypt', failed=0)
    r = client.post('/auth/login', json={'email': 'hash@test.com', 'password': 'Correcta.2026*'})
    assert r.status_code == 401, r.get_json()
