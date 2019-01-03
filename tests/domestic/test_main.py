import base64
import json
from asyncio import sleep
from time import time
from urllib.parse import parse_qs, urlparse

from aiohttp import WSMsgType
from async_timeout import timeout
from cryptography.fernet import Fernet

from em2 import VERSION
from em2.core import Components, Verbs

from ..conftest import AnyInt, CloseToNow, RegexStr


async def test_valid_cookie_list_convs(cli, conv, url, db_conn):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'key': conv.key,
        'subject': 'Test Conversation',
        'published': False,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'snippet': None,
    }] == obj


async def test_list_no_convs(cli, url, db_conn):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [] == obj


async def test_no_cookie(cli, url):
    cli.session.cookie_jar.clear()
    r = await cli.get(url('list'))
    assert r.headers['Access-Control-Allow-Origin'] == 'https://frontend.example.com'
    assert r.status == 401, await r.text()
    assert {'error': 'cookie missing or invalid'} == await r.json()


async def test_access_control_good(cli, url):
    r = await cli.options(url('list'), headers={
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
        'Origin': 'https://frontend.example.com',
    })
    assert r.status == 200, await r.text()
    assert 'ok' == await r.text()


async def test_access_control_wrong(cli, url):
    r = await cli.options(url('list'), headers={
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
        'Origin': 'https://frontend.wrong.com',
    })
    assert r.status == 403, await r.text()
    obj = await r.json()
    assert {'error': 'Access-Control checks failed'} == obj


async def test_invalid_cookie(cli, url, settings):
    fernet = Fernet(base64.urlsafe_b64encode(b'i am different and 32 bits long!'))
    settings = cli.server.app['settings']
    cookies = {settings.cookie_name: fernet.encrypt(b'foobar').decode()}
    cli.session.cookie_jar.update_cookies(cookies)

    r = await cli.get(url('list'))
    assert r.status == 401, await r.text()
    assert {'error': 'cookie missing or invalid'} == await r.json()


async def test_expired_cookie(cli, url, settings):
    fernet = Fernet(settings.auth_session_secret)
    data = f'123:{int(time()) - 3600}:foo@bar.com'
    cookies = {settings.cookie_name: fernet.encrypt(data.encode()).decode()}
    cli.session.cookie_jar.update_cookies(cookies)

    r = await cli.get(url('list'), allow_redirects=False)
    assert r.status == 307, await r.text()
    assert r.headers['Location'].startswith(f'{settings.auth_server_url}/update-session/?r=')
    return_url = parse_qs(urlparse(r.headers['Location']).query)['r'][0]
    assert return_url == f'http://127.0.0.1:{cli.server.port}{url("list")}'


async def test_list_conv(cli, conv, url):
    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['key'] == conv.key


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
    conv_id, conv_key, snippet, pub = await db_conn.fetchrow('SELECT id, key, snippet, published FROM conversations')
    assert {'key': conv_key} == await r.json()
    assert conv_key.startswith('dft-')
    assert not pub
    assert {
        'addr': 'testing@example.com',
        'body': 'this is a message',
        'comp': None,
        'msgs': 1,
        'prts': 2,
        'verb': 'create',
    } == json.loads(snippet)
    v = await db_conn.fetch('SELECT address FROM recipients as r '
                            'JOIN participants as p ON r.id = p.recipient '
                            'WHERE p.conv = $1', conv_id)
    assert {r['address'] for r in v} == {'testing@example.com', 'other@example.com'}


async def test_create_conv_custom_keys(cli, url, db_conn):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
        'conv_key': 'dft-0123456789abcefg',
        'msg_key': 'msg-0123456789abcefg',
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    assert {'key': 'dft-0123456789abcefg'} == await r.json()
    assert conv_key == 'dft-0123456789abcefg'
    msg_key = await db_conn.fetchval('SELECT key FROM messages')
    assert msg_key == 'msg-0123456789abcefg'


async def test_create_conv_custom_keys_wrong(cli, url):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
        'conv_key': 'dft-123',
        'msg_key': 'msg-0123456789abcefG',
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 400, await r.text()
    assert {
        'conv_key': {
            'error_msg': 'invalid key',
            'error_type': 'ValueError',
            'track': 'str'
        },
        'msg_key': {
            'error_msg': 'key must be lower case',
            'error_type': 'ValueError',
            'track': 'str'
        },
    } == await r.json()


async def test_create_conv_repeat_keys(cli, url):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
        'conv_key': 'dft-0123456789abcefg',
        'msg_key': 'msg-0123456789abcefg',
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    r = await cli.post(url('create'), json=data)
    assert r.status == 409, await r.text()


async def test_create_publish_conv(cli, url, db_conn):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
        'publish': True
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    conv_key, published = await db_conn.fetchrow('SELECT key, published FROM conversations')
    assert {'key': conv_key} == await r.json()
    assert published
    assert not conv_key.startswith('dft-')

    r = await cli.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 4
    assert {
        'key': await db_conn.fetchval("SELECT key FROM actions WHERE verb='publish'"),
        'verb': 'publish',
        'component': None,
        'body': 'Test Subject',
        'timestamp': CloseToNow(),
        'actor': 'testing@example.com',
        'parent': RegexStr('^act-.*'),
        'message': None,
        'participant': None,
    } == actions[3]


async def test_get_draft_conv(cli, url, db_conn):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
    }
    r = await cli.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    conv_key = (await r.json())['key']
    r = await cli.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    msg_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='message'")
    prt1_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant' ORDER BY id LIMIT 1")
    prt2_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant' ORDER BY id DESC LIMIT 1")
    assert [
        {
            'key': msg_key,
            'verb': 'add',
            'component': 'message',
            'body': 'this is a message',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': None,
            'message': await db_conn.fetchval("SELECT key FROM messages"),
            'participant': None,
        },
        {
            'key': prt1_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': msg_key,
            'message': None,
            'participant': 'testing@example.com',
        },
        {
            'key': prt2_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': prt1_key,
            'message': None,
            'participant': 'other@example.com',
        },
        {
            'key': await db_conn.fetchval("SELECT key FROM actions WHERE verb='create'"),
            'verb': 'create',
            'component': None,
            'body': 'Test Subject',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': prt2_key,
            'message': None,
            'participant': None,
        },
    ] == actions
    r = await cli.get(url('get', conv=f'{conv_key[:10]}'))
    assert r.status == 200, await r.text()
    actions2 = await r.json()
    assert actions == actions2


async def test_add_message_not_published(cli, conv, url):
    data = {'body': 'hello'}
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 400, await r.text()
    assert 'extra messages cannot be added to draft conversations' == await r.text()


async def test_publish_conv(cli, conv, url, db_conn):
    published, ts1 = await db_conn.fetchrow('SELECT published, created_ts FROM conversations')
    assert not published
    await sleep(0.01)
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key, published, ts2 = await db_conn.fetchrow('SELECT key, published, created_ts FROM conversations')
    assert {'key': new_conv_key} == await r.json()
    assert new_conv_key != conv.key
    assert published
    assert ts2 > ts1

    r = await cli.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    msg_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='message'")
    prt_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant'")
    assert [
        {
            'key': msg_key,
            'verb': 'add',
            'component': 'message',
            'body': 'this is the message',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': None,
            'message': await db_conn.fetchval('SELECT key FROM messages'),
            'participant': None,
        },
        {
            'key': prt_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': msg_key,
            'message': None,
            'participant': 'testing@example.com',
        },
        {
            'key': await db_conn.fetchval("SELECT key FROM actions WHERE verb='publish'"),
            'verb': 'publish',
            'component': None,
            'body': 'Test Conversation',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': prt_key,
            'message': None,
            'participant': None,
        },
    ] == actions


async def test_add_message(cli, conv, url, db_conn):
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']
    parent_key = await db_conn.fetchval("SELECT key FROM actions where component='message'")
    data = {'body': 'hello', 'parent': parent_key}
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    debug(url_)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert {
        'key': RegexStr('act-.*'),
        'conv_key': new_conv_key,
        'verb': 'add',
        'component': 'message',
        'ts': CloseToNow(),
        'parent': parent_key,
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
        'parent': AnyInt(),
        'recipient': None,
        'message': await db_conn.fetchval("SELECT id FROM messages WHERE body = 'hello'"),
        'body': 'hello',
    } == action
    snippet = json.loads(await db_conn.fetchval('SELECT snippet FROM conversations'))
    assert {
        'addr': 'testing@example.com',
        'body': 'hello',
        'comp': 'message',
        'msgs': 2,
        'prts': 1,
        'verb': 'add',
    } == snippet


async def test_list_with_snippet(cli, conv, url, db_conn):
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']

    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'key': await db_conn.fetchval('SELECT key from conversations'),
        'subject': 'Test Conversation',
        'published': True,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'snippet': {
            'addr': 'testing@example.com',
            'body': 'this is the message',
            'comp': None,
            'msgs': 1,
            'prts': 1,
            'verb': 'publish',
        },
    }] == obj

    parent_key = await db_conn.fetchval("SELECT key FROM actions where component='message'")
    data = {'body': 'hello', 'parent': parent_key}
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'key': await db_conn.fetchval('SELECT key from conversations'),
        'subject': 'Test Conversation',
        'published': True,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'snippet': {
            'addr': 'testing@example.com',
            'body': 'hello',
            'comp': 'message',
            'msgs': 2,
            'prts': 1,
            'verb': 'add',
        },
    }] == obj


async def test_add_message_missing(cli, url):
    url_ = url('act', conv='x' * 20, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_)
    assert r.status == 404, await r.text()
    assert {'error': 'conversation xxxxxxxxxxxxxxxxxxxx not found'} == await r.json()


async def test_add_message_invalid_data_list(cli, conv, url):
    data = [
        'subject',
    ]
    url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 400, await r.text()
    assert {'error': 'request json should be a dictionary'} == await r.json()


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
    "track": "ConstrainedStrValue"
  }
}""" == text


async def test_add_message_get(cli, conv, url, db_conn):
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']
    parent_key = await db_conn.fetchval("SELECT key FROM actions where component='message'")
    data = {'body': 'reply', 'relationship': 'sibling', 'parent': parent_key}
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    new_msg_key = await db_conn.fetchval("SELECT key FROM messages WHERE body = 'reply'")
    prt_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant'")
    msg1_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='message' ORDER BY id LIMIT 1")
    pub_key = await db_conn.fetchval("SELECT key FROM actions WHERE verb='publish'")
    msg2_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='message' ORDER BY id DESC LIMIT 1")
    assert [
        {
            'key': msg1_key,
            'verb': 'add',
            'component': 'message',
            'body': 'this is the message',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': None,
            'message': 'msg-firstmessagekeyx',
            'participant': None,
        },
        {
            'key': prt_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': msg1_key,
            'message': None,
            'participant': 'testing@example.com',
        },
        {
            'actor': 'testing@example.com',
            'body': 'Test Conversation',
            'component': None,
            'key': pub_key,
            'message': None,
            'parent': prt_key,
            'participant': None,
            'timestamp': CloseToNow(),
            'verb': 'publish'
        },
        {
            'actor': conv.creator_address,
            'body': 'reply',
            'component': 'message',
            'key': msg2_key,
            'message': new_msg_key,
            'parent': msg1_key,
            'participant': None,
            'timestamp': CloseToNow(),
            'verb': 'add'
        }
    ] == actions


async def test_add_prt_get(cli, conv, url, db_conn):
    assert None is await db_conn.fetchval('SELECT snippet FROM conversations')
    data = {'item': 'other@example.com'}
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli.get(url('get', conv=conv.key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert [
        {
            'actor': conv.creator_address,
            'body': None,
            'component': 'participant',
            'key': await db_conn.fetchval("SELECT key FROM actions"),
            'message': None,
            'parent': None,
            'participant': 'other@example.com',
            'timestamp': CloseToNow(),
            'verb': 'add'
        }
    ] == actions


async def test_get_conv_actions(cli, conv, url, db_conn):
    r = await cli.get(url('get', conv=conv.key))
    assert r.status == 200, await r.text()
    assert [] == await r.json()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']
    pub_act_key = await db_conn.fetchval("SELECT key FROM actions where verb='publish'")
    msg1_act_key = await db_conn.fetchval("SELECT key FROM actions where component='message'")
    prt1_act_key = await db_conn.fetchval("SELECT key FROM actions where component='participant'")

    r = await cli.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert [
        (msg1_act_key, 'add', 'message', 'this is the message'),
        (prt1_act_key, 'add', 'participant', None),
        (pub_act_key, 'publish', None, 'Test Conversation'),
    ] == [(a['key'], a['verb'], a['component'], a['body']) for a in actions], actions

    add_url = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(add_url, json={'body': 'hello', 'parent': msg1_act_key})
    assert r.status == 200, await r.text()
    msg2_act_key = (await r.json())['key']
    r = await cli.post(add_url, json={'body': 'hello again', 'parent': msg2_act_key})
    assert r.status == 200, await r.text()
    msg3_act_key = (await r.json())['key']

    add_prt_url = url('act', conv=new_conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(add_prt_url, json={'item': 'other@example.com'})
    assert r.status == 200, await r.text()
    prt2_act_key = (await r.json())['key']

    r = await cli.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    # debug(actions)
    assert [
        (msg1_act_key, 'add', 'message', 'this is the message'),
        (prt1_act_key, 'add', 'participant', None),
        (pub_act_key, 'publish', None, 'Test Conversation'),
        (msg2_act_key, 'add', 'message', 'hello'),
        (msg3_act_key, 'add', 'message', 'hello again'),
        (prt2_act_key, 'add', 'participant', None),
    ] == [(a['key'], a['verb'], a['component'], a['body']) for a in actions], actions

    r = await cli.get(url('get', conv=new_conv_key, query={'since': msg2_act_key}))
    assert r.status == 200, await r.text()
    assert [
        (msg3_act_key, 'add', 'message', 'hello again'),
        (prt2_act_key, 'add', 'participant', None),
    ] == [(a['key'], a['verb'], a['component'], a['body']) for a in await r.json()], actions


async def test_publish_conv_foreign_part(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 200, await r.text()

    assert not await db_conn.fetchval('SELECT published FROM conversations')

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert await db_conn.fetchval('SELECT published FROM conversations')

    assert foreign_server.app['request_log'] == [
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
        'POST /auth/ > 201',
        RegexStr('POST /create/[0-9a-f]+/ > 204'),
    ], foreign_server.app['request_log']


async def test_publish_add_msg_conv(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 200, await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert foreign_server.app['request_log'] == [
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
        'POST /auth/ > 201',
        RegexStr('POST /create/[0-9a-f]+/ > 204'),
    ], foreign_server.app['request_log']

    new_conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    parent = await db_conn.fetchval("SELECT key FROM actions where component='message'")
    r = await cli.post(url_, json={'parent': parent, 'body': 'hello'})
    assert r.status == 200, await r.text()

    assert foreign_server.app['request_log'] == [
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
        'POST /auth/ > 201',
        RegexStr(f'POST /create/{new_conv_key}/ > 204'),
        RegexStr(f'POST /{new_conv_key}/message/add/msg-[0-9a-z]+ > 201'),
    ], foreign_server.app['request_log']


async def test_publish_update_add_part(cli, conv, url, db_conn, foreign_server):
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'other@foreign.com'})
    assert r.status == 200, await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()

    assert foreign_server.app['request_log'] == [
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
        'POST /auth/ > 201',
        RegexStr('POST /create/[0-9a-f]+/ > 204'),
    ], foreign_server.app['request_log']

    new_conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    url_ = url('act', conv=new_conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json={'item': 'new@foreign.com'})
    assert r.status == 200, await r.text()
    assert foreign_server.app['request_log'] == [
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
        'POST /auth/ > 201',
        RegexStr(f'POST /create/{new_conv_key}/ > 204'),
        'GET /check-user-node/ > 200',
        RegexStr(f'POST /{new_conv_key}/participant/add/new@foreign.com > 201'),
    ], foreign_server.app['request_log']


async def test_publish_domestic_push(cli, conv, url, db_conn):
    async with cli.session.ws_connect(cli.make_url('/ws/')) as ws:
        assert not await db_conn.fetchval('SELECT published FROM conversations')
        await cli.server.app['background'].ready.wait()
        r = await cli.post(url('publish', conv=conv.key))
        assert r.status == 200, await r.text()
        assert await db_conn.fetchval('SELECT published FROM conversations')

        got_message = False
        with timeout(0.5):
            async for msg in ws:
                assert msg.type == WSMsgType.text
                data = json.loads(msg.data)
                assert data['component'] is None
                assert data['verb'] == 'publish'
                assert data['actor'] == conv.creator_address
                got_message = True
                break
        assert not ws.closed
        assert ws.close_code is None
        assert got_message


async def test_not_published_domestic_push(cli, conv, url, db_conn):
    async with cli.session.ws_connect(cli.make_url('/ws/')) as ws:
        await cli.server.app['background'].ready.wait()
        url_ = url('act', conv=conv.key, component=Components.MESSAGE, verb=Verbs.MODIFY)
        r = await cli.post(url_, json={
            'body': 'different content',
            'item': conv.first_msg_key,
        })
        assert r.status == 200, await r.text()
        assert 'different content' == await db_conn.fetchval('SELECT body FROM messages')

        got_message = False
        with timeout(0.5):
            async for msg in ws:
                assert msg.type == WSMsgType.text
                data = json.loads(msg.data)
                assert data['component'] == 'message'
                assert data['verb'] == 'modify'
                assert data['actor'] == conv.creator_address
                assert data['key'].startswith('act-')
                got_message = True
                break
        assert got_message


async def test_ws_anon(cli):
    cli.session.cookie_jar.clear()
    async with cli.session.ws_connect(cli.make_url('/ws/')) as ws:
        got_message = False
        with timeout(0.5):
            async for _ in ws:  # noqa (underscore is unused)
                got_message = True
        assert ws.closed
        assert ws.close_code == 4403
        assert got_message is False


async def test_ws_expired(cli, settings):
    fernet = Fernet(settings.auth_session_secret)
    data = f'123:{int(time()) - 3600}:foo@bar.com'
    cookies = {settings.cookie_name: fernet.encrypt(data.encode()).decode()}
    cli.session.cookie_jar.update_cookies(cookies)
    async with cli.session.ws_connect(cli.make_url('/ws/')) as ws:
        got_message = False
        with timeout(0.5):
            async for msg in ws:
                assert msg.type == WSMsgType.text
                assert msg.data == '{"auth_url": "http://auth.example.com/update-session/"}'
                got_message = True
        assert ws.closed
        assert ws.close_code == 4401
        assert got_message


async def test_index_anon(cli, url):
    cli.session.cookie_jar.clear()
    r = await cli.get(url('index'))
    assert r.headers['Access-Control-Allow-Origin'] == 'https://frontend.example.com'
    assert r.status == 200, await r.text()
    assert f'em2 v{VERSION}:- domestic interface\n' == await r.text()


async def test_index_auth(cli, url):
    r = await cli.get(url('index'))
    assert r.status == 200, await r.text()
    assert f'em2 v{VERSION}:- domestic interface\n' == await r.text()


async def test_missing_url(cli):
    r = await cli.get('/foobar/')
    assert r.status == 404, await r.text()


async def test_prts_publish(cli, conv, url, db_conn):
    data = {'item': 'other@example.com'}
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']

    r = await cli.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    # debug(actions)
    pub_key = await db_conn.fetchval("SELECT key FROM actions WHERE verb='publish'")
    msg_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='message'")
    prt1_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant' ORDER BY id LIMIT 1")
    prt2_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='participant' ORDER BY id DESC LIMIT 1")
    assert [
        {
            'key': msg_key,
            'verb': 'add',
            'component': 'message',
            'body': 'this is the message',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': None,
            'message': await db_conn.fetchval("SELECT key FROM messages"),
            'participant': None,
        },
        {
            'key': prt1_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': msg_key,
            'message': None,
            'participant': 'testing@example.com',
        },
        {
            'key': prt2_key,
            'verb': 'add',
            'component': 'participant',
            'body': None,
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': prt1_key,
            'message': None,
            'participant': 'other@example.com',
        },
        {
            'key': pub_key,
            'verb': 'publish',
            'component': None,
            'body': 'Test Conversation',
            'timestamp': CloseToNow(),
            'actor': 'testing@example.com',
            'parent': prt2_key,
            'message': None,
            'participant': None,
        },
    ] == actions


async def test_view_unpublished(cli, conv, url, extra_cli):
    cli2 = await extra_cli('another@example.com')

    r = await cli2.get(url('get', conv=conv.key))
    assert r.status == 404, await r.text()

    data = {'item': 'another@example.com'}
    url_ = url('act', conv=conv.key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli2.get(url('get', conv=conv.key))
    assert r.status == 403, await r.text()
    assert 'conversation is unpublished' in await r.text()

    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']

    r = await cli2.get(url('get', conv=new_conv_key))
    assert r.status == 200, await r.text()


async def test_view_when_deleted(cli, conv, url, extra_cli):
    r = await cli.post(url('publish', conv=conv.key))
    assert r.status == 200, await r.text()
    new_conv_key = (await r.json())['key']
    get_url = url('get', conv=new_conv_key)

    cli2 = await extra_cli('another@example.com')

    r = await cli2.get(get_url)
    assert r.status == 404, await r.text()  # not yet added

    data = {'item': 'another@example.com'}
    url_ = url('act', conv=new_conv_key, component=Components.PARTICIPANT, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli2.get(get_url)
    assert r.status == 200, await r.text()  # now added to conv
    actions = await r.json()
    assert len(actions) == 4, actions

    data = {'item': 'another@example.com'}
    url_ = url('act', conv=new_conv_key, component=Components.PARTICIPANT, verb=Verbs.DELETE)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli2.get(get_url)
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 5, actions

    data = {'body': 'hello', 'parent': actions[0]['key']}
    url_ = url('act', conv=new_conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await cli.post(url_, json=data)
    assert r.status == 200, await r.text()

    r = await cli.get(get_url)
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 6, actions

    r = await cli2.get(get_url)
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 5, actions

    # both since and deleted limit
    r = await cli2.get(url('get', conv=new_conv_key, query={'since': actions[1]['key']}))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 3, actions


async def test_modify_subject(post_create_conv, cli, url, db_conn):
    conv_key = await post_create_conv(publish=True)
    r = await cli.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 3
    assert 'Test Subject' == await db_conn.fetchval('SELECT subject FROM conversations')
    pub_action_key = actions[-1]['key']

    url_ = url('act', conv=conv_key, component=Components.SUBJECT, verb=Verbs.MODIFY)
    r = await cli.post(url_, json={
        'body': 'different subject',
        'parent': actions[-1]['key'],
    })
    assert r.status == 200, await r.text()
    assert 'different subject' == await db_conn.fetchval('SELECT subject FROM conversations')

    r = await cli.get(url('get', conv=conv_key))
    assert r.status == 200, await r.text()
    actions = await r.json()
    assert len(actions) == 4
    new_action_key = await db_conn.fetchval("SELECT key FROM actions WHERE component='subject'")
    assert {
        'key': new_action_key,
        'verb': 'modify',
        'component': 'subject',
        'body': 'different subject',
        'timestamp': CloseToNow(),
        'actor': 'testing@example.com',
        'parent': pub_action_key,
        'message': None,
        'participant': None,
    }


async def test_modify_subject_repeat(post_create_conv, cli, url, db_conn):
    conv_key = await post_create_conv()
    url_ = url('act', conv=conv_key, component=Components.SUBJECT, verb=Verbs.MODIFY)
    r = await cli.post(url_, json={
        'body': 'subject 2',
        'parent': await db_conn.fetchval("SELECT key FROM actions WHERE verb='create'"),
    })
    assert r.status == 200, await r.text()
    assert 'subject 2' == await db_conn.fetchval('SELECT subject FROM conversations')

    r = await cli.post(url_, json={
        'body': 'subject 3',
        'parent': await db_conn.fetchval("SELECT key FROM actions WHERE component='subject'"),
    })
    assert r.status == 200, await r.text()
    assert 'subject 3' == await db_conn.fetchval('SELECT subject FROM conversations')


async def test_modify_subject_wrong_key(post_create_conv, cli, url, db_conn):
    conv_key = await post_create_conv()

    url_ = url('act', conv=conv_key, component=Components.SUBJECT, verb=Verbs.MODIFY)
    r = await cli.post(url_, json={
        'body': 'different subject',
        'parent': await db_conn.fetchval("SELECT key FROM actions WHERE component='message'"),
    })
    assert r.status == 400, await r.text()


async def test_modify_subject_wrong_verb(post_create_conv, cli, url, db_conn):
    conv_key = await post_create_conv()

    url_ = url('act', conv=conv_key, component=Components.SUBJECT, verb=Verbs.ADD)
    r = await cli.post(url_, json={
        'body': 'different subject',
        'parent': await db_conn.fetchval("SELECT key FROM actions WHERE verb='create'"),
    })
    assert r.status == 400, await r.text()
