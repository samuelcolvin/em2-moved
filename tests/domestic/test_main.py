import base64
import json
from asyncio import sleep

from aiohttp import WSMsgType
from async_timeout import timeout
from cryptography.fernet import Fernet

from em2.core import Components, Verbs
from em2.utils.encoding import msg_encode

from ..conftest import AnyInt, CloseToNow, RegexStr, python_dict, timestamp_regex  # noqa


async def test_valid_cookie_list_convs(cli, conv, url, db_conn):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'key': conv.key,
        'subject': 'Test Conversation',
        'published': False,
        'ts': CloseToNow()
    }] == obj


async def test_list_no_convs(cli, url, db_conn):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [] == obj


async def test_no_cookie(cli, url):
    cli.session.cookie_jar.clear()
    r = await cli.get(url('list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_invalid_cookie(cli, url, settings):
    data = {'address': 'testing@example.com'}
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(b'i am different and 32 bits long!'))
    settings = cli.server.app['settings']
    cookies = {settings.COOKIE_NAME: fernet.encrypt(data).decode()}
    cli.session.cookie_jar.update_cookies(cookies)

    r = await cli.get(url('list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_session_update(cli, url):
    assert len(cli.session.cookie_jar) == 1
    c1 = list(cli.session.cookie_jar)[0]

    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 2
    c2 = list(cli.session.cookie_jar)[-1]

    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 2
    c3 = list(cli.session.cookie_jar)[-1]
    assert c1 != c2
    print(c2)
    print(c3)
    assert c2 == c3


async def test_list_conv(cli, conv, url):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['key'] == conv.key


async def test_get_conv(cli, conv, url):
    r = await cli.get(url('get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['details']['subject'] == 'Test Conversation'
    assert obj['messages'][0]['body'] == 'this is the message'

    # should work when start of key
    r = await cli.get(url('get', conv=conv.key[:-1]))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['details']['subject'] == 'Test Conversation'


async def test_missing_conv(cli, conv, url):
    r = await cli.get(url('get', conv=conv.key + 'x'))
    assert r.status == 404, await r.text()
    assert 'key12345678x not found' in await r.text()


async def test_create_conv(cli, url, db_conn):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    assert {'url': f'/c/{conv_key}/'} == await r.json()
    assert conv_key.startswith('dft-')


async def test_add_message(cli, conv, url, db_conn):
    data = {
        'body': 'hello',
    }
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 201, await r.text()
    obj = await r.json()
    assert {
        'key': RegexStr('act-.*'),
        'conv_key': 'key12345678',
        'verb': 'add',
        'component': 'message',
        'ts': timestamp_regex,
        'parent': None,
        'relationship': None,
        'body': 'hello',
        'item': RegexStr('msg-.*'),
    } == obj
    action_key = obj['key']
    action = dict(await db_conn.fetchrow('SELECT * FROM actions WHERE key = $1', action_key))
    assert {
        'id': AnyInt(),
        'conv': conv.id,
        'key': action_key,
        'verb': 'add',
        'component': 'message',
        'timestamp': CloseToNow(),
        'actor': await db_conn.fetchval('SELECT id FROM recipients'),
        'parent': None,
        'recipient': None,
        'message': await db_conn.fetchval("SELECT id FROM messages WHERE body = 'hello'"),
        'body': 'hello',
    } == action


async def test_add_message_missing(cli, url):
    url_ = url('act', conv='x' * 20, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_)
    assert r.status == 404, await r.text()
    text = await r.text()
    assert text.startswith('conversation xxxxxxxxxxxxxxxxxxxx not found')


async def test_add_message_invalid_data_list(cli, conv, url):
    data = [
        'subject',
    ]
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 400, await r.text()
    text = await r.text()
    assert 'request json should be a dictionary' == text


async def test_add_message_invalid_data_model_error(cli, conv, url):
    data = {'parent': 'X' * 21}
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
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


async def test_add_message_get(cli, conv, url, db_conn):
    data = {'item': 'msg-firstmessagekeyx', 'body': 'reply', 'relationship': 'sibling'}
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 201, await r.text()

    r = await cli.get(url('get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    new_msg_key = await db_conn.fetchval("SELECT key FROM messages WHERE body = 'reply'")
    print(python_dict(obj))
    assert {
        'actions': [
            {
                'actor': conv.creator_address,
                'body': 'reply',
                'component': 'message',
                'key': await db_conn.fetchval('SELECT key FROM actions'),
                'message': new_msg_key,
                'parent': None,
                'participant': None,
                'ts': CloseToNow(),
                'verb': 'add'
            }
        ],
        'details': {
            'creator': conv.creator_address,
            'key': 'key12345678',
            'published': False,
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'deleted': False,
                'after': None,
                'body': 'this is the message',
                'relationship': None,
                'key': 'msg-firstmessagekeyx'
            },
            {
                'deleted': False,
                'after': 'msg-firstmessagekeyx',
                'body': 'reply',
                'relationship': 'sibling',
                'key': new_msg_key
            }
        ],
        'participants': [
            {
                'address': conv.creator_address,
            }
        ]
    } == obj


async def test_add_part_get(cli, conv, url, db_conn):
    data = {'item': 'other@example.com'}
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 201, await r.text()

    r = await cli.get(url('get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert {
        'actions': [
            {
                'actor': conv.creator_address,
                'body': None,
                'component': 'participant',
                'key': await db_conn.fetchval("SELECT key FROM actions"),
                'message': None,
                'parent': None,
                'participant': 'other@example.com',
                'ts': CloseToNow(),
                'verb': 'add'
            }
        ],
        'details': {
            'creator': conv.creator_address,
            'key': 'key12345678',
            'published': False,
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'deleted': False,
                'after': None,
                'body': 'this is the message',
                'relationship': None,
                'key': 'msg-firstmessagekeyx'
            }
        ],
        'participants': [
            {'address': conv.creator_address},
            {'address': 'other@example.com'}
        ]
    } == obj


async def test_publish_conv(cli, conv, url, db_conn):
    published, ts1 = await db_conn.fetchrow('SELECT published, timestamp FROM conversations')
    assert not published
    await sleep(0.01)
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key, published, ts2 = await db_conn.fetchrow('SELECT key, published, timestamp FROM conversations')
    assert {'key': new_conv_key} == await r.json()
    assert new_conv_key != conv.key
    assert published
    assert ts2 > ts1
    action = dict(await db_conn.fetchrow('SELECT * FROM actions'))
    assert {
        'id': AnyInt(),
        'conv': conv.id,
        'key': RegexStr(r'^pub-.*'),
        'verb': 'add',
        'component': 'participant',
        'timestamp': CloseToNow(),
        'actor': await db_conn.fetchval('SELECT id FROM recipients'),
        'parent': None,
        'recipient': None,
        'message': None,
        'body': None,
    } == action


async def test_publish_conv_foreign_part(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 201, await r.text()

    assert not await db_conn.fetchval('SELECT published FROM conversations')

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert await db_conn.fetchval('SELECT published FROM conversations')

    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr('POST /[0-9a-f]+/participant/add/ > 201'),
    ]


async def test_publish_add_msg_conv(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 201, await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr('POST /[0-9a-f]+/participant/add/ > 201'),
    ]

    new_conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'msg-firstmessagekeyx', 'body': 'hello'})
    assert r.status == 201, await r.text()

    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr(f'POST /{new_conv_key}/participant/add/ > 201'),
        RegexStr(f'POST /{new_conv_key}/message/add/msg-[0-9a-z]+ > 201'),
    ]


async def test_publish_update_add_part(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 201, await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr('POST /[0-9a-f]+/participant/add/ > 201'),
    ]

    new_conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    url_ = url('act', conv=new_conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'new@foreign.com'})
    assert r.status == 201, await r.text()
    print(foreign_server.app['request_log'])
    assert foreign_server.app['request_log'] == [
        'POST /authenticate > 201',
        RegexStr(f'POST /{new_conv_key}/participant/add/ > 201'),
        RegexStr(f'POST /{new_conv_key}/participant/add/new@foreign.com > 201'),
    ]


async def test_publish_domestic_push(cli, conv, url, db_conn, debug):
    async with cli.session.ws_connect(cli.make_url('/ws/')) as ws:
        assert not await db_conn.fetchval('SELECT published FROM conversations')
        await cli.server.app['background'].ready.wait()
        r = await cli.post(url('publish', conv=conv.key))
        assert r.status == 200, await r.text()
        assert await db_conn.fetchval('SELECT published FROM conversations')

        got_message = False
        # FIXME this fails occasionally with the ws message never being received
        with timeout(0.5):
            async for msg in ws:
                assert msg.tp == WSMsgType.text
                data = json.loads(msg.data)
                assert data['component'] == 'participant'
                assert data['verb'] == 'add'
                assert data['actor'] == conv.creator_address
                got_message = True
                break
        assert got_message


async def test_get_latest_conv(cli, create_conv, url, db_conn):
    # times will be identical here as CURRENT_TIMESTAMP doesn't change within a transaction, ordering will be on id
    await create_conv(key='xxxxxxxxxxa', subject='conv1')
    await create_conv(key='xxxxxxxxxxc', subject='conv3')
    await create_conv(key='xxxxxxxxxxb', subject='conv2')
    r = await cli.get(url('get', conv='x' * 8))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['details']['subject'] == 'conv2'
