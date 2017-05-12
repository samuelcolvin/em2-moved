import base64
from datetime import datetime

from cryptography.fernet import Fernet
from pydantic.datetime_parse import parse_datetime

from em2.core import Components, Verbs
from em2.utils.encoding import msg_encode


async def test_valid_cookie(dclient, conv_key, url):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    ts = parse_datetime(obj[0].pop('ts'))
    assert 0.0 < (datetime.now() - ts).total_seconds() < 1
    obj[0].pop('id')
    assert [{'key': conv_key, 'subject': 'Test Conversation'}] == obj


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
    action.pop('id')
    action.pop('conversation')
    ts = action.pop('timestamp')
    assert 0.0 < (datetime.now() - ts).total_seconds() < 1
    assert {
        'key': action_key,
        'verb': 'add',
        'component': 'message',
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
    # obj = await r.json()
    # import json
    # print(json.dumps(obj, indent=2, sort_keys=True))
