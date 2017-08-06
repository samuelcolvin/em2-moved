from datetime import datetime

from arq.utils import to_unix_ms

from em2 import Settings
from em2.utils.network import check_server

from .fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE


async def test_add_message(fclient, db_conn, url):
    addr = 'test@already-authenticated.com'
    recipient_id = await db_conn.fetchval('INSERT INTO recipients (address) VALUES ($1) RETURNING id', addr)
    conv_key = 'key123'
    args = conv_key, recipient_id, 'Test Conversation', 'test-conv'
    conv_id = await db_conn.fetchval('INSERT INTO conversations (key, creator, subject, ref) '
                                     'VALUES ($1, $2, $3, $4) RETURNING id', *args)
    await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, recipient_id)
    msg_key = 'msg-firstmessagekeyx'
    args = msg_key, conv_id, 'this is the message'
    await db_conn.execute('INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)', *args)

    url_ = url('act', conv=conv_key, component='message', verb='add', item=msg_key)
    r = await fclient.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': addr,
        'em2-timestamp': datetime.now().strftime('%s'),
        'em2-action-key': 'x' * 20,
    })
    assert r.status == 201, await r.text()
    assert await r.text() == ''

    # TODO test the new message & action look right


async def test_conv_missing(fclient, url):
    url = url('act', conv='123', component='message', verb='add', item='')
    r = await fclient.post(url, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 204


async def test_wrong_conv(fclient, db_conn, url):
    addr = 'test@already-authenticated.com'
    recipient_id = await db_conn.fetchval('INSERT INTO recipients (address) VALUES ($1) RETURNING id', addr)
    conv_key = 'key123'
    args = conv_key, recipient_id, 'Test Conversation', 'test-conv'
    conv_id = await db_conn.fetchval('INSERT INTO conversations (key, creator, subject, ref) '
                                     'VALUES ($1, $2, $3, $4) RETURNING id', *args)
    await db_conn.execute('INSERT INTO participants (conv, recipient) VALUES ($1, $2)', conv_id, recipient_id)
    msg_key = 'msg-firstmessagekeyx'
    args = msg_key, conv_id, 'this is the message'
    await db_conn.execute('INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)', *args)

    url_ = url('act', conv=conv_key, component='message', verb='add', item=msg_key)
    r = await fclient.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'other@already-authenticated.com',
        'em2-timestamp': datetime.now().strftime('%s'),
        'em2-action-key': 'x' * 20,
    })
    assert r.status == 403, await r.text()
    assert await r.text() == '"other@already-authenticated.com" is not a participant in this conversation'


async def test_check_server(fclient):
    r = await check_server(Settings(WEB_PORT=fclient.server.port), expected_status=404)
    assert r == 0
    r = await check_server(Settings(WEB_PORT=fclient.server.port + 1), expected_status=404)
    assert r == 1


async def test_no_headers(fclient, url):
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''))
    assert r.status == 400, await r.text()
    assert 'header "em2-auth" missing' == await r.text()


async def test_bad_auth_token(fclient, url):
    headers = {
        'em2-auth': '123',
        'em2-actor': 'test@example.com',
        'em2-timestamp': '123',
        'em2-action-key': '123',
    }

    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 403, await r.text()
    assert await r.text() == 'invalid token'


async def test_domain_mismatch(fclient, url):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@example.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
        'em2-action-key': '123',
    }
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 403, await r.text()
    assert await r.text() == '"example.com" does not use "already-authenticated.com"'


async def test_authenticate(fclient, url):
    headers = {
        'em2-platform': PLATFORM,
        'em2-timestamp': str(TIMESTAMP),
        'em2-signature': VALID_SIGNATURE
    }
    r = await fclient.post(url('authenticate'), headers=headers)
    assert r.status == 201, await r.text()
    key = r.headers['em2-key']
    assert key.startswith('foobar.com:2461536000:')
    assert len(key) == 86


async def test_authenticate_wrong_fields(fclient, url):
    headers = {
        'em2-platform': PLATFORM,
        'em2-timestamp': str(TIMESTAMP),
    }
    r = await fclient.post(url('authenticate'), headers=headers)
    assert r.status == 400, await r.text()
    data = await r.json()
    assert data['em2-signature']['error_msg'] == 'field required'


async def test_authenticate_failed(fclient, url):
    headers = {
        'em2-platform': 'wham.com',
        'em2-timestamp': str(TIMESTAMP),
        'em2-signature': VALID_SIGNATURE
    }
    r = await fclient.post(url('authenticate'), headers=headers)
    assert r.status == 400
    assert await r.text() == 'invalid signature\n'
