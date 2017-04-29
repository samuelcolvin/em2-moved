from datetime import datetime, timedelta

from em2 import Settings
from em2.comms import encoding
from em2.core import Action, Components, Verbs
from em2.utils import check_server, to_unix_ms
from tests.fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE

EXAMPLE_HEADERS = {
    'em2-auth': 'already-authenticated.com:123:whatever',
    'em2-address': 'test@already-authenticated.com',
    'em2-timestamp': '1',
    'em2-event-id': '123',
}


async def test_add_message(client):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await client.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    conv_ds = client.em2_ctrl.ds.new_conv_ds(conv_id, None)
    msg1_id = list(conv_ds.conv_obj['messages'])[0]
    ts = action.timestamp + timedelta(seconds=1)
    action2 = Action('test@already-authenticated.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=ts)
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': str(to_unix_ms(ts)),
        'em2-event-id': action2.calc_event_id(),
    }
    data = {
        'parent_id': msg1_id,
        'body': 'reply',
    }
    r = await client.post('/{}/messages/add/'.format(conv_id), data=encoding.encode(data), headers=headers)
    assert r.status == 201, await r.text()
    assert await r.text() == '\n'


async def test_check_server(client):
    r = await check_server(Settings(WEB_PORT=client.server.port))
    assert r == 0
    r = await check_server(Settings(WEB_PORT=client.server.port + 1))
    assert r == 1


async def test_no_headers(client):
    r = await client.post('/123/messages/add/')
    assert r.status == 400
    assert await r.text() == 'Missing Headers: em2-auth, em2-address, em2-timestamp, em2-event-id\n'


async def test_bad_auth_token(client):
    headers = {
        'em2-auth': '123',
        'em2-address': 'test@example.com',
        'em2-timestamp': '123',
        'em2-event-id': '123',
    }
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 403
    assert await r.text() == 'Invalid auth header\n'


async def test_domain_miss_match(client):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@example.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
        'em2-event-id': '123',
    }
    r = await client.post('/123/messages/add/', headers=headers)
    assert await r.text() == '"example.com" does not use "already-authenticated.com"\n'
    assert r.status == 403


async def test_missing_field(client):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
    }
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 400
    assert await r.text() == 'Missing Headers: em2-event-id\n'


async def test_bad_timezone(client):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timezone': 'invalid',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
        'em2-event-id': '123',
    }
    r = await client.post('/123/messages/add/', headers=headers)
    assert await r.text() == 'Unknown timezone "invalid"\n'
    assert r.status == 400


async def test_bad_timestamp(client):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': 'foobar',
        'em2-event-id': '123',
    }
    r = await client.post('/123/messages/add/', headers=headers)
    assert await r.text() == 'Invalid timestamp "foobar"\n'
    assert r.status == 400


async def test_missing_conversation(client):
    ts = datetime.now()
    action2 = Action('test@already-authenticated.com', '123', Verbs.ADD, Components.MESSAGES, timestamp=ts)
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': str(to_unix_ms(ts)),
        'em2-event-id': action2.calc_event_id(),
    }
    data = {
        'parent_id': '123',
        'body': 'reply',
    }
    r = await client.post('/123/messages/add/', data=encoding.encode(data), headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_data(client):
    data = 'foobar'
    r = await client.post('/123/messages/add/', data=data, headers=EXAMPLE_HEADERS)
    assert r.status == 400
    assert await r.text() == 'Error Decoding msgpack: unpack(b) received extra data.\n'


async def test_valid_data_list(client):
    r = await client.post('/123/messages/add/', data=encoding.encode([1, 2, 3]), headers=EXAMPLE_HEADERS)
    assert r.status == 400
    assert await r.text() == 'request data is not a dictionary\n'


async def test_authenticate(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/authenticate', data=encoding.encode(data))
    assert r.status == 201
    r = encoding.decode(await r.read())
    assert isinstance(r, dict)
    assert list(r.keys()) == ['key']
    assert r['key'].startswith('foobar.com:2461536000:')
    assert len(r['key']) == 86


async def test_authenticate_bad_data(client):
    r = await client.post('/authenticate', data='not data')
    assert r.status == 400
    assert await r.text() == 'error decoding data: unpack(b) received extra data.\n'


async def test_authenticate_wrong_fields(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
    }
    r = await client.post('/authenticate', data=encoding.encode(data))
    assert r.status == 400
    assert await r.text() == '{"signature": ["required field"]}\n'


async def test_authenticate_failed(client):
    data = {
        'platform': 'wham.com',
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/authenticate', data=encoding.encode(data))
    assert r.status == 400
    assert await r.text() == 'invalid signature\n'


async def test_invalid_data_field(client):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await client.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    ts = action.timestamp + timedelta(seconds=1)
    Action('test@already-authenticated.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=ts)
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-event-id': '123',
    }
    r = await client.post('/{}/messages/add/'.format(conv_id), data=encoding.encode([1, 2, 3]), headers=headers)
    assert r.status == 400, await r.text()
    assert await r.text() == 'request data is not a dictionary\n'
