import bcrypt

from em2 import VERSION


async def test_index(cli, url):
    r = await cli.get(url('index'))
    assert r.status == 200, await r.text()
    assert f'em2 v{VERSION}:- auth interface\n' == await r.text()


async def test_get_accept_invitation(cli, url, token):
    url_ = url('accept-invitation', query=dict(token=token(first_name='foobar')))
    r = await cli.get(url_)
    assert r.status == 200, await r.text()
    data = await r.json()
    assert {
        'msg': 'please submit password',
        'fields': {
            'address': 'testing@example.com',
            'first_name': 'foobar',
            'last_name': None,
            'recovery_address': None
        }
    } == data


async def test_get_accept_invitation_invalid_token(cli, url):
    url_ = url('accept-invitation', query=dict(token='foobar'))
    r = await cli.get(url_)
    assert r.status == 403, await r.text()
    assert 'Invalid token' == await r.text()


async def test_post_accept_invitation(cli, url, token, auth_db_conn):
    url_ = url('accept-invitation', query=dict(token=token(first_name='foobar')))
    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 200, await r.text()
    data = await r.json()
    assert {'msg': 'user created'} == data
    address, first_name, pw_hash = await auth_db_conn.fetchrow(
        'SELECT address, first_name, password_hash FROM auth_users'
    )
    assert address == 'testing@example.com'
    assert first_name == 'foobar'
    assert bcrypt.checkpw(b'thisissecure', pw_hash.encode())
    assert not bcrypt.checkpw(b'thisis not secure', pw_hash.encode())
    # TODO test logged in


async def test_user_exists(cli, url, token, auth_db_conn):
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')
    url_ = url('accept-invitation', query=dict(token=token(first_name='foobar')))
    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 200, await r.text()
    assert 1 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')

    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 409, await r.text()
    assert 1 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')
