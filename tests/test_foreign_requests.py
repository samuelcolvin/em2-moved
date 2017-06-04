# flake8: noqa  (until we sort references to old objects)
from datetime import datetime, timedelta

import pytest

from em2 import Settings
from em2.utils.encoding import msg_encode, to_unix_ms
from em2.utils.network import check_server

# from em2.core import Action, Components, Verbs
from .fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE

EXAMPLE_HEADERS = {
    'em2-auth': 'already-authenticated.com:123:whatever',
    'em2-address': 'test@already-authenticated.com',
    'em2-timestamp': '1',
    'em2-event-id': '123',
}


@pytest.mark.xfail
async def test_add_message(fclient):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await fclient.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    conv_ds = fclient.em2_ctrl.ds.new_conv_ds(conv_id, None)
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
    r = await fclient.post('/{}/messages/add/'.format(conv_id), data=msg_encode(data), headers=headers)
    assert r.status == 201, await r.text()
    assert await r.text() == '\n'


async def test_check_server(fclient):
    r = await check_server(Settings(WEB_PORT=fclient.server.port), expected_status=404)
    assert r == 0
    r = await check_server(Settings(WEB_PORT=fclient.server.port + 1), expected_status=404)
    assert r == 1

async def test_no_headers(fclient, url):
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''))
    assert r.status == 400
    assert await r.text() == ('Invalid Headers:\n'
                              'em2-auth: missing\n'
                              'em2-address: missing\n'
                              'em2-timestamp: missing\n'
                              'em2-event-id: missing\n')


async def test_bad_auth_token(fclient, url):
    headers = {
        'em2-auth': '123',
        'em2-address': 'test@example.com',
        'em2-timestamp': '123',
        'em2-event-id': '123',
    }

    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 403
    assert await r.text() == 'Invalid auth header\n'


async def test_domain_mismatch(fclient, url):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@example.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
        'em2-event-id': '123',
    }
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert await r.text() == '"example.com" does not use "already-authenticated.com"\n'
    assert r.status == 403


async def test_missing_field(fclient, url):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
    }
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 400
    assert await r.text() == 'Invalid Headers:\nem2-event-id: missing\n'


async def test_bad_timestamp(fclient, url):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': 'foobar',
        'em2-event-id': '123',
    }
    r = await fclient.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert await r.text() == "Invalid Headers:\nem2-timestamp: invalid literal for int() with base 10: 'foobar'\n"
    assert r.status == 400


@pytest.mark.xfail
async def test_missing_conversation(fclient, url):
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
    url = url('act', conv='123', component='message', verb='add', item='')
    r = await fclient.post(url, data=msg_encode(data), headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_data(fclient, url):
    data = 'foobar'
    url = url('act', conv='123', component='message', verb='add', item='')
    r = await fclient.post(url, data=data, headers=EXAMPLE_HEADERS)
    assert r.status == 400
    assert await r.text() == 'Error Decoding msgpack: unpack(b) received extra data.\n'


async def test_valid_data_list(fclient, url):
    url = url('act', conv='123', component='message', verb='add', item='')
    r = await fclient.post(url, data=msg_encode([1, 2, 3]), headers=EXAMPLE_HEADERS)
    assert r.status == 400
    assert await r.text() == 'request data is not a dictionary\n'


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
    assert r.status == 400
    assert await r.text() == 'Invalid Headers:\nem2-signature: missing\n'


async def test_authenticate_failed(fclient, url):
    headers = {
        'em2-platform': 'wham.com',
        'em2-timestamp': str(TIMESTAMP),
        'em2-signature': VALID_SIGNATURE
    }
    r = await fclient.post(url('authenticate'), headers=headers)
    assert r.status == 400
    assert await r.text() == 'invalid signature\n'


@pytest.mark.xfail
async def test_invalid_data_field(fclient, url):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await fclient.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    ts = action.timestamp + timedelta(seconds=1)
    Action('test@already-authenticated.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=ts)
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-address': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-event-id': '123',
    }
    url = url('act', conv=conv_id, component='message', verb='add', item='')
    r = await fclient.post(url, data=msg_encode([1, 2, 3]), headers=headers)
    assert r.status == 400, await r.text()
    assert await r.text() == 'request data is not a dictionary\n'
