"""
Admin de solo lectura (rol 'viewer', pedido del usuario 2026-10-29): ve todo
lo que ve el admin en las dos tiendas, pero no puede modificar nada.
"""
from tests.test_multi_store import app, _token, _headers  # noqa: F401  (fixture app)


def test_solo_lectura_ve_como_admin_en_las_dos_tiendas(app, client):
    token = _token(app, 7, 'viewer')
    for store in ('carreno', 'primavera'):
        assert client.get('/api/expenses?year=2026&month=10', headers=_headers(token, store)).status_code == 200
        assert client.get('/api/accounts', headers=_headers(token, store)).status_code == 200
    stores = client.get('/api/stores', headers=_headers(token)).get_json()
    assert {s['code'] for s in stores['stores']} == {'carreno', 'primavera'}
    user = client.get('/auth/verify', headers=_headers(token)).get_json()['user']
    assert user['role'] == 'admin' and user['read_only'] is True


def test_solo_lectura_no_puede_modificar_nada(app, client):
    token = _token(app, 7, 'viewer')
    h = _headers(token, 'primavera')
    for method, path in [('post', '/api/expenses'), ('post', '/api/accounts/manual-adjustment'),
                         ('post', '/api/sum_payments'), ('post', '/api/users'),
                         ('put', '/api/users/1'), ('delete', '/api/users/1'),
                         ('post', '/api/users/change-password')]:
        r = getattr(client, method)(path, json={'x': 1}, headers=h)
        assert r.status_code == 403, (method, path)
        assert r.get_json()['read_only'] is True
    # El admin normal sigue pudiendo
    admin = _headers(_token(app, 1, 'admin'), 'primavera')
    assert client.post('/api/expenses', json={}, headers=admin).status_code != 403


def test_se_puede_crear_un_usuario_de_solo_lectura(app, client):
    admin = _headers(_token(app, 1, 'admin'))
    r = client.post('/api/users', json={'email': 'lector@test.com', 'password': 'Lector.2026*',
                                         'name': 'Lector', 'role': 'viewer'}, headers=admin)
    assert r.status_code == 201, r.get_json()
    login = client.post('/auth/login', json={'email': 'lector@test.com', 'password': 'Lector.2026*'}).get_json()
    assert login['user']['role'] == 'viewer' and login['user']['read_only'] is True
    assert {s['code'] for s in login['user']['stores']} == {'carreno', 'primavera'}
