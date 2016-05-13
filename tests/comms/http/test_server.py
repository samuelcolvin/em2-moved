import json

from em2.core import Action, Verbs
from tests.fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE

GOOD_HEADERS = {
    'Authorization': 'Token already-authenticated.com:123:whatever',
    'Actor': 'test@already-authenticated.com',
}

async def test_add_message(client):
    action = Action('test@already-authenticated.com', None, Verbs.ADD)
    conv_id = await client.em2_ctrl.act(action, subject='foo bar', body='hi, how are you?')
    conv_ds = client.em2_ctrl.ds.new_conv_ds(conv_id, None)
    msg1_id = list(conv_ds.conv_obj['messages'])[0]
    data = '{"parent_id": "%s", "body": "reply"}' % msg1_id
    r = await client.post('/-/{}/messages/add/'.format(conv_id), data=data, headers=GOOD_HEADERS)
    assert r.status == 201
    text = await r.text()
    assert text == '\n'


async def test_no_auth_header(client):
    r = await client.post('/-/123/messages/add/')
    assert r.status == 400
    content = await r.read()
    assert content == b'No "Authorization" header found\n'


async def test_no_actor_header(client):
    headers = {'Authorization': 'Token 321'}
    r = await client.post('/-/123/messages/add/', headers=headers)
    assert r.status == 400
    content = await r.read()
    assert content == b'No "Actor" header found\n'


async def test_bad_token(client):
    headers = {'Authorization': 'Token 321', 'Actor': 'test@example.com'}
    r = await client.post('/-/123/messages/add/', headers=headers)
    assert r.status == 403
    content = await r.read()
    assert content == b'Invalid Authorization token\n'


async def test_domain_miss_match(client):
    headers = {'Authorization': 'Token already-authenticated.com:123:whatever', 'Actor': 'test@example.com'}
    r = await client.post('/-/123/messages/add/', headers=headers)
    assert r.status == 403
    content = await r.read()
    assert content == b'"example.com" does not use "already-authenticated.com"\n'


async def test_missing_conversation(client):
    r = await client.post('/-/123/messages/add/', headers=GOOD_HEADERS)
    assert r.status == 400
    content = await r.read()
    assert content == b"BadDataException: missing a required argument: 'body'\n"


async def test_missing_conversation_valid_html(client):
    data = '{"body": "foobar", "parent_id": "123"}'
    r = await client.post('/-/123/messages/add/', data=data, headers=GOOD_HEADERS)
    assert r.status == 400
    content = await r.read()
    assert content == b'ConversationNotFound: conversation 123 not found\n'


async def test_invalid_json(client):
    data = 'foobar'
    r = await client.post('/-/123/messages/add/', data=data, headers=GOOD_HEADERS)
    assert r.status == 400
    content = await r.read()
    assert content == b'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_valid_json_list(client):
    data = '[1, 2, 3]'
    r = await client.post('/-/123/messages/add/', data=data, headers=GOOD_HEADERS)
    assert r.status == 400
    content = await r.read()
    assert content == b'request data is not a dictionary\n'


async def test_authenticate(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/-/authenticate', data=json.dumps(data))
    assert r.status == 201
    text = await r.text()
    assert text.startswith('{"key": "foobar.com:2461536000:')
    assert len(text) == 97


async def test_authenticate_bad_json(client):
    r = await client.post('/-/authenticate', data='not json')
    assert r.status == 400
    assert await r.text() == 'Error Decoding JSON: Expecting value: line 1 column 1 (char 0)\n'


async def test_authenticate_wrong_fields(client):
    data = {
        'platform': PLATFORM,
        'timestamp': TIMESTAMP,
    }
    r = await client.post('/-/authenticate', data=json.dumps(data))
    assert r.status == 400
    assert await r.text() == '{"signature": "required field"}\n'


async def test_authenticate_failed(client):
    data = {
        'platform': 'wham.com',
        'timestamp': TIMESTAMP,
        'signature': VALID_SIGNATURE
    }
    r = await client.post('/-/authenticate', data=json.dumps(data))
    assert r.status == 400
    assert await r.text() == 'invalid signature\n'
