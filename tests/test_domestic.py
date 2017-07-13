import base64
import json
from asyncio import sleep

from aiohttp import WSMsgType
from cryptography.fernet import Fernet

from em2.core import Components, Verbs
from em2.utils.encoding import msg_encode

from .conftest import AnyInt, CloseToNow, RegexStr, python_dict  # noqa


async def test_valid_cookie_list_convs(dclient, conv_key, url, db_conn):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'id': await db_conn.fetchval('SELECT id FROM recipients'),
        'key': conv_key,
        'subject': 'Test Conversation',
        'published': False,
        'ts': CloseToNow()
    }] == obj


async def test_no_cookie(dclient, url):
    dclient.session.cookie_jar.clear()
    r = await dclient.get(url('list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_invalid_cookie(dclient, url, settings):
    data = {'address': 'testing@example.com'}
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(b'i am different and 32 bits long!'))
    settings = dclient.server.app['settings']
    cookies = {settings.COOKIE_NAME: fernet.encrypt(data).decode()}
    dclient.session.cookie_jar.update_cookies(cookies)

    r = await dclient.get(url('list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_session_update(dclient, url):
    assert len(dclient.session.cookie_jar) == 1
    c1 = list(dclient.session.cookie_jar)[-1]

    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    assert len(dclient.session.cookie_jar) == 2
    c2 = list(dclient.session.cookie_jar)[-1]

    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    assert len(dclient.session.cookie_jar) == 2
    c3 = list(dclient.session.cookie_jar)[-1]
    assert c1 != c2
    assert c2 == c3


async def test_list_conv(dclient, conv_key, url):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['key'] == conv_key


async def test_get_conv(dclient, conv_key, url):
    r = await dclient.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['details']['subject'] == 'Test Conversation'
    assert obj['messages'][0]['body'] == 'this is the message'


async def test_missing_conv(dclient, conv_key, url):
    r = await dclient.get(url('get', conv=conv_key + 'x'))
    assert r.status == 404, await r.text()
    assert 'key123x not found' in await r.text()


async def test_create_conv(dclient, url, db_conn):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
    }
    r = await dclient.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    assert {'url': f'/c/{conv_key}/'} == await r.json()
    assert conv_key.startswith('draft-')


async def test_add_message(dclient, conv_key, url, db_conn):
    data = {
        'item': 'msg-firstmessage_key',
        'body': 'hello',
    }
    url_ = url('act', conv=conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 201, await r.text()
    obj = await r.json()
    assert {
        'key': RegexStr('act-.*'),
        'conv_key': 'key123',
        'verb': 'add',
        'component': 'message',
        'timestamp': RegexStr(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d.\d{1,6}'),
        'parent': None,
        'relationship': None,
        'body': 'hello',
        'item': RegexStr('msg-.*'),
    } == obj
    action_key = obj['key']
    action = dict(await db_conn.fetchrow('SELECT * FROM actions WHERE key = $1', action_key))
    assert {
        'id': AnyInt(),
        'conv': AnyInt(),
        'key': action_key,
        'verb': 'add',
        'component': 'message',
        'timestamp': CloseToNow(),
        'actor': await db_conn.fetchval("SELECT id FROM participants"),
        'parent': None,
        'part': None,
        'message': await db_conn.fetchval("SELECT id FROM messages WHERE body = 'hello'"),
        'body': 'hello',
    } == action


async def test_add_message_missing(dclient, url):
    url_ = url('act', conv='xxx', component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_)
    assert r.status == 404, await r.text()
    text = await r.text()
    assert text.startswith('conversation xxx not found')


async def test_add_message_invalid_data_list(dclient, conv_key, url):
    data = [
        'subject',
        'item',
    ]
    url_ = url('act', conv=conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 400, await r.text()
    text = await r.text()
    assert 'request json should be a dictionary' == text


async def test_add_message_invalid_data_model_error(dclient, conv_key, url):
    data = {'parent': 'X' * 21}
    url_ = url('act', conv=conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 400, await r.text()
    text = await r.text()
    assert """\
{
  "parent": {
    "error_msg": "length greater than maximum allowed: 20",
    "error_type": "ValueError",
    "index": null,
    "track": "ConstrainedStrValue"
  }
}""" == text


async def test_add_message_get(dclient, conv_key, url, db_conn):
    data = {'item': 'msg-firstmessage_key', 'body': 'reply', 'relationship': 'sibling'}
    url_ = url('act', conv=conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 201, await r.text()

    r = await dclient.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    new_msg_id = await db_conn.fetchval("SELECT key FROM messages WHERE body = 'reply'")
    assert {
        'actions': [
            {
                'actor': 'testing@example.com',
                'body': 'reply',
                'component': 'message',
                'key': await db_conn.fetchval('SELECT key FROM actions'),
                'message': new_msg_id,
                'parent': None,
                'participant': None,
                'timestamp': CloseToNow(),
                'verb': 'add'
            }
        ],
        'details': {
            'creator': 'testing@example.com',
            'key': 'key123',
            'published': False,
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'active': True,
                'after': None,
                'body': 'this is the message',
                'relationship': None,
                'key': 'msg-firstmessage_key'
            },
            {
                'active': True,
                'after': 'msg-firstmessage_key',
                'body': 'reply',
                'relationship': 'sibling',
                'key': new_msg_id
            }
        ],
        'participants': [
            {
                'address': 'testing@example.com',
                'readall': False
            }
        ]
    } == obj


async def test_add_part_get(dclient, conv_key, url, db_conn):
    data = {'item': 'other@example.com'}
    url_ = url('act', conv=conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 201, await r.text()

    r = await dclient.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert {
        'actions': [
            {
                'actor': 'testing@example.com',
                'body': None,
                'component': 'participant',
                'key': await db_conn.fetchval("SELECT key FROM actions"),
                'message': None,
                'parent': None,
                'participant': 'other@example.com',
                'timestamp': CloseToNow(),
                'verb': 'add'
            }
        ],
        'details': {
            'creator': 'testing@example.com',
            'key': 'key123',
            'published': False,
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'active': True,
                'after': None,
                'body': 'this is the message',
                'relationship': None,
                'key': 'msg-firstmessage_key'
            }
        ],
        'participants': [
            {'address': 'testing@example.com', 'readall': False},
            {'address': 'other@example.com', 'readall': False}
        ]
    } == obj


async def test_publish_conv(dclient, conv_key, url, db_conn, redis):
    published, ts1 = await db_conn.fetchrow('SELECT published, timestamp FROM conversations')
    assert not published
    await sleep(0.01)
    r = await dclient.post(url('publish', conv=conv_key))
    assert r.status == 200, await r.text()
    new_conv_key, published, ts2 = await db_conn.fetchrow('SELECT key, published, timestamp FROM conversations')
    assert {'key': new_conv_key} == await r.json()
    assert new_conv_key != conv_key
    assert published
    assert ts2 > ts1
    action = dict(await db_conn.fetchrow('SELECT * FROM actions'))
    assert {
        'id': AnyInt(),
        'conv': AnyInt(),
        'key': RegexStr(r'^pub-.*'),
        'verb': 'add',
        'component': 'participant',
        'timestamp': CloseToNow(),
        'actor': await db_conn.fetchval('SELECT id FROM participants'),
        'parent': None,
        'part': None,
        'message': None,
        'body': None,
    } == action


async def test_publish_conv_foreign_part(dclient, conv_key, url, db_conn, redis, foreign_server):
    url_ = url('act', conv=conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await dclient.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 201, await r.text()

    assert not await db_conn.fetchval('SELECT published FROM conversations')

    r = await dclient.post(url('publish', conv=conv_key))
    assert r.status == 200, await r.text()

    assert await db_conn.fetchval('SELECT published FROM conversations')

    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr('POST /[0-9a-f]+/participant/add/ > 201'),
    ]


async def test_action_received_via_ws(dclient, db_conn, redis):
    async with dclient.session.ws_connect(dclient.make_url('/ws/')) as ws:
        job_data = {
            'recipients': [
                await db_conn.fetchval('SELECT id FROM recipients')
            ],
            'action': 'foobar',
        }
        await redis.lpush('frontend:jobs:d-testing', msg_encode(job_data))
        async for msg in ws:
            assert msg.tp == WSMsgType.text
            data = json.loads(msg.data)
            assert data == 'foobar'
            break
