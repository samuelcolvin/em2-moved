import base64

from cryptography.fernet import Fernet

from em2.core import Components, Verbs
from em2.utils.encoding import msg_encode
from .conftest import AnyInt, CloseToNow, python_dict  # noqa


async def test_valid_cookie(dclient, conv_key, url, db_conn):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert [{
        'id': await db_conn.fetchval('SELECT id FROM recipients'),
        'key': conv_key,
        'subject': 'Test Conversation',
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


async def test_create_conv(dclient, url):
    data = {
        'subject': 'Test Subject',
        'message': 'this is a message',
        'participants': [
            'other@example.com',
        ],
    }
    r = await dclient.post(url('create'), json=data)
    assert r.status == 201, await r.text()
    # obj = await r.json()
    # print(obj)


async def test_add_message(dclient, conv_key, url, db_conn):
    data = {
        'item': 'msg-firstmessage_key',
        'body': 'hello',
    }
    url_ = url('act', conv=conv_key, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 201, await r.text()
    obj = await r.json()
    action_key = obj['key']
    action = dict(await db_conn.fetchrow('SELECT * FROM actions WHERE key = $1', action_key))
    assert {
        'id': AnyInt(),
        'conversation': AnyInt(),
        'key': action_key,
        'verb': 'add',
        'component': 'message',
        'timestamp': CloseToNow(),
        'actor': await db_conn.fetchval("SELECT id FROM participants"),
        'parent': None,
        'participant': None,
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
    data = {'item': 'msg-firstmessage_key', 'body': 'reply'}
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
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'active': True,
                'after': None,
                'body': 'this is the message',
                'child': False,
                'key': 'msg-firstmessage_key'
            },
            {
                'active': True,
                'after': 'msg-firstmessage_key',
                'body': 'reply',
                'child': False,
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
            'subject': 'Test Conversation',
            'ts': CloseToNow()
        },
        'messages': [
            {
                'active': True,
                'after': None,
                'body': 'this is the message',
                'child': False,
                'key': 'msg-firstmessage_key'
            }
        ],
        'participants': [
            {'address': 'testing@example.com', 'readall': False},
            {'address': 'other@example.com', 'readall': False}
        ]
    } == obj