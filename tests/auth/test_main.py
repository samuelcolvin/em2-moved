import json

import bcrypt
import pytest

from em2 import VERSION
from tests.conftest import CloseToNow, IsUUID, RegexStr

from .conftest import TEST_ADDRESS, TEST_PASSWORD


async def test_index(cli, url):
    r = await cli.get(url('index'))
    assert r.status == 200, await r.text()
    assert f'em2 v{VERSION}:- auth interface\n' == await r.text()


async def test_get_accept_invitation(cli, url, inv_token):
    url_ = url('accept-invitation', query=dict(token=inv_token(first_name='foobar')))
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
    assert {'error': 'Invalid token'} == await r.json()


async def test_post_accept_invitation(cli, url, inv_token, auth_db_conn):
    assert len(cli.session.cookie_jar) == 0
    url_ = url('accept-invitation', query=dict(token=inv_token(first_name='foobar')))
    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 200, await r.text()
    data = await r.json()
    assert {'msg': 'user created'} == data
    assert len(cli.session.cookie_jar) == 1
    c = r.headers['Set-Cookie']
    assert c.startswith('em2session=')
    address, first_name, pw_hash = await auth_db_conn.fetchrow(
        'SELECT address, first_name, password_hash FROM auth_users'
    )
    assert address == 'testing@example.com'
    assert first_name == 'foobar'
    assert bcrypt.checkpw(b'thisissecure', pw_hash.encode())
    assert not bcrypt.checkpw(b'thisis not secure', pw_hash.encode())
    # TODO test logged in


async def test_user_exists(cli, url, inv_token, auth_db_conn):
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')
    url_ = url('accept-invitation', query=dict(token=inv_token(first_name='foobar')))
    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 200, await r.text()
    assert 1 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')

    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 409, await r.text()
    assert 1 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')


async def test_password_not_secure1(cli, url, inv_token, auth_db_conn):
    assert len(cli.session.cookie_jar) == 0
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')
    url_ = url('accept-invitation', query=dict(token=inv_token(first_name='foobar')))
    r = await cli.post(url_, json={'password': 'testing'})
    assert r.status == 400, await r.text()
    data = await r.json()
    assert data['msg'] == 'password not strong enough'
    assert data['feedback']['warning'] == 'This is a very common password.'
    assert len(cli.session.cookie_jar) == 0


async def test_password_not_secure2(cli, url, inv_token, auth_db_conn):
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(id) FROM auth_users')
    url_ = url('accept-invitation', query=dict(token=inv_token(first_name='samuel')))
    r = await cli.post(url_, json={'password': 'samuel'})
    assert r.status == 400, await r.text()
    data = await r.json()
    assert data['msg'] == 'password not strong enough'
    assert data['feedback']['warning'] == 'Names and surnames by themselves are easy to guess.'


async def test_login_get(cli, url, user):
    # address, password = user
    r = await cli.get(url('login'))
    assert r.status == 200, await r.text()
    assert {'msg': 'login', 'captcha_required': False} == await r.json()
    assert len(cli.session.cookie_jar) == 0


async def test_login_post_successful(cli, url, auth_db_conn, user):
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(*) FROM auth_sessions')
    address, password = user
    r = await cli.post(url('login'), json={'address': address, 'password': password})
    assert r.status == 200, await r.text()
    assert {'msg': 'login successful'} == await r.json()
    assert len(cli.session.cookie_jar) == 1
    assert 1 == await auth_db_conn.fetchval('SELECT COUNT(*) FROM auth_sessions')
    r = dict(await auth_db_conn.fetchrow('SELECT * FROM auth_sessions'))
    events = r.pop('events')
    assert {
        'token': IsUUID(),
        'auth_user': await auth_db_conn.fetchval('SELECT id FROM auth_users'),
        'started': CloseToNow(),
        'last_active': CloseToNow(),
        'active': True,
    } == r
    assert len(events) == 1
    event = json.loads(events[0])
    assert {
        'ac': 'login',
        'ip': '127.0.0.1',
        'ts': CloseToNow(),
        'ua': RegexStr('Python.*'),
    } == event


@pytest.mark.parametrize('address, password', [
    (TEST_ADDRESS, 'foobar'),
    ('foo@bar.com', TEST_PASSWORD),
    ('foo@bar.com', 'foobar'),
])
async def test_failed_login(cli, url, user, auth_db_conn, address, password):
    r = await cli.post(url('login'), json={'address': address, 'password': password})
    assert r.status == 403, await r.text()
    assert {'error': 'invalid credentials', 'captcha_required': False} == await r.json()
    assert 0 == len(cli.session.cookie_jar)
    assert 0 == await auth_db_conn.fetchval('SELECT COUNT(*) FROM auth_sessions')


async def test_captcha_required(cli, settings, url, user):
    for _ in range(settings.easy_login_attempts):
        r = await cli.get(url('login'))
        assert r.status == 200, await r.text()
        assert {'msg': 'login', 'captcha_required': False} == await r.json(), await r.text()

        r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar'})
        assert r.status == 403, await r.text()
        assert {'error': 'invalid credentials', 'captcha_required': False} == await r.json(), await r.text()

    for _ in range(5):
        r = await cli.get(url('login'))
        assert r.status == 200, await r.text()
        assert {'msg': 'login', 'captcha_required': True} == await r.json(), await r.text()

        r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar'})
        assert r.status == 429, await r.text()
        assert {'error': 'captcha required', 'captcha_required': True} == await r.json(), await r.text()


async def test_captcha_supplied(cli, settings, url, user, g_recaptcha_server):
    address, password = user
    for _ in range(settings.easy_login_attempts):
        r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar'})
        assert r.status == 403, await r.text()

    r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar'})
    assert r.status == 429, await r.text()

    g_bad, g_good = 'bad' + 'x' * 20,  'good' + 'x' * 20
    r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar', 'grecaptcha': g_bad})
    assert r.status == 400, await r.text()
    assert {'error': 'invalid captcha'} == await r.json()

    r = await cli.post(url('login'), json={'address': 'foo@bar.com', 'password': 'foobar', 'grecaptcha': g_good})
    assert r.status == 403, await r.text()
    assert {'error': 'invalid credentials', 'captcha_required': True} == await r.json()

    r = await cli.post(url('login'), json={'address': address, 'password': password, 'grecaptcha': g_good})
    assert r.status == 200, await r.text()
    assert {'msg': 'login successful'} == await r.json()


async def test_get_account(cli, url, authenticate):
    r = await cli.get(url('account'))
    assert r.status == 200, await r.text()
    assert {
        'address': 'testing@example.com',
        'first_name': None,
        'last_name': 'testing',
        'recovery_address': None,
        'otp_enabled': False
    } == await r.json()


async def test_view_sessions(cli, url, authenticate):
    r = await cli.get(url('sessions'))
    assert r.status == 200, await r.text()
    assert {
        'active': True,
        'last_active': CloseToNow(),
        'events': [
            {
                'ac': 'user created',
                'ip': '127.0.0.1',
                'ts': CloseToNow(),
                'ua': RegexStr('Python.*')
            },
            {
                'ac': 'request',
                'ip': '127.0.0.1',
                'ts': CloseToNow(),
                'ua': RegexStr('Python.*')
            }
        ]
    } == await r.json()


async def test_get_account_anon(cli, url):
    r = await cli.get(url('account'))
    assert r.status == 403, await r.text()
    assert {'error': 'cookie missing or invalid'} == await r.json()


async def test_update_session(cli, url, authenticate):
    assert len(cli.session.cookie_jar) == 1
    c1 = list(cli.session.cookie_jar)[0]
    r = await cli.get(url('account'))
    assert r.status == 200, await r.text()
    assert c1 == list(cli.session.cookie_jar)[0]

    r = await cli.get(url('update-session', query={'r': 'https://example.com/foo/bar/?a=b'}), allow_redirects=False)
    assert r.status == 307
    assert r.headers['Location'] == 'https://example.com/foo/bar/?a=b'
    assert len(cli.session.cookie_jar) == 1
    assert c1 != list(cli.session.cookie_jar)[0]


async def test_update_session_no_redirect(cli, url, authenticate):
    r = await cli.get(url('update-session'), allow_redirects=False)
    assert r.status == 400, await r.text()


async def test_logout(cli, url, authenticate):
    r = await cli.get(url('account'))
    assert r.status == 200, await r.text()

    r = await cli.post(url('logout'))
    assert r.status == 200, await r.text()

    r = await cli.get(url('account'))
    assert r.status == 403, await r.text()


async def test_logout_keep_cookie(cli, url, authenticate):
    r = await cli.get(url('account'))
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 1
    c = list(cli.session.cookie_jar)[0]

    r = await cli.post(url('logout'))
    assert r.status == 200, await r.text()

    assert len(cli.session.cookie_jar) == 0
    cli.session.cookie_jar.update_cookies({c.key: c.value})

    r = await cli.get(url('account'))
    assert r.status == 403, await r.text()
