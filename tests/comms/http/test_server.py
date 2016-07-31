import json
from datetime import timedelta, datetime

from em2.core import Action, Verbs, Components
from em2.utils import to_unix_timestamp
from tests.fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE

AUTH_HEADER = {
    'Authorization': 'Token already-authenticated.com:123:whatever',
}

async def test_add_message(client):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await client.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    conv_ds = client.em2_ctrl.ds.new_conv_ds(conv_id, None)
    msg1_id = list(conv_ds.conv_obj['messages'])[0]
    ts = action.timestamp + timedelta(seconds=1)
    action2 = Action('test@already-authenticated.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=ts)
    data = {
        'address': 'test@already-authenticated.com',
        'timestamp': to_unix_timestamp(ts),
        'event_id': action2.calc_event_id(),
        'kwargs': {
            'parent_id': msg1_id,
            'body': 'reply',
        }
    }
    r = await client.post('/{}/messages/add/'.format(conv_id), data=json.dumps(data), headers=AUTH_HEADER)
    assert r.status == 201
    assert await r.text() == '\n'


async def test_no_auth_header(client):
    r = await client.post('/123/messages/add/')
    assert r.status == 400
    assert await r.text() == 'No "Authorization" header found\n'


async def test_bad_token(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    r = await client.post('/123/messages/add/', headers=headers)
    assert r.status == 403
    assert await r.text() == 'Invalid Authorization token\n'


async def test_domain_miss_match(client):
    data = {
        'address': 'test@example.com',
        'timestamp': 123,
        'event_id': '123',
        'kwargs': {
            'parent_id': '123',
            'body': 'reply',
        }
    }
    r = await client.post('/123/messages/add/', data=json.dumps(data), headers=AUTH_HEADER)
    assert await r.text() == '"example.com" does not use "already-authenticated.com"\n'
    assert r.status == 403


async def test_missing_field(client):
    data = {
        'address': 'test@already-authenticated.com',
        'timestamp': 123,
    }
    r = await client.post('/123/messages/add/', data=json.dumps(data), headers=AUTH_HEADER)
    assert r.status == 400
    assert await r.text() == '{"event_id": "required field"}\n'


async def test_missing_conversation(client):
    ts = datetime.now()
    action2 = Action('test@already-authenticated.com', '123', Verbs.ADD, Components.MESSAGES, timestamp=ts)
    data = {
        'address': 'test@already-authenticated.com',
        'timestamp': to_unix_timestamp(ts),
        'event_id': action2.calc_event_id(),
        'kwargs': {
            'parent_id': '123',
            'body': 'reply',
        }
    }
    r = await client.post('/123/messages/add/', data=json.dumps(data), headers=AUTH_HEADER)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_json(client):
    data = 'foobar'
    r = await client.post('/123/messages/add/', data=data, headers=AUTH_HEADER)
    assert r.status == 400
    assert await r.text() == 'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_valid_json_list(client):
    data = '[1, 2, 3]'
    r = await client.post('/123/messages/add/', data=data, headers=AUTH_HEADER)
    assert r.status == 400
    assert await r.text() == 'request data is not a dictionary\n'


async def test_authenticate(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/authenticate', data=json.dumps(data))
    assert r.status == 201
    text = await r.text()
    assert text.startswith('{"key": "foobar.com:2461536000:')
    assert len(text) == 97


async def test_authenticate_bad_json(client):
    r = await client.post('/authenticate', data='not json')
    assert r.status == 400
    assert await r.text() == 'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_authenticate_wrong_fields(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
    }
    r = await client.post('/authenticate', data=json.dumps(data))
    assert r.status == 400
    assert await r.text() == '{"signature": "required field"}\n'


async def test_authenticate_failed(client):
    data = {
        'platform': 'wham.com',
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/authenticate', data=json.dumps(data))
    assert r.status == 400
    assert await r.text() == 'invalid signature\n'
