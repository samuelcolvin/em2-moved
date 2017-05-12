import base64
from datetime import datetime

from cryptography.fernet import Fernet
from pydantic.datetime_parse import parse_datetime

from em2.core import Components, Verbs
from em2.utils.encoding import msg_encode


async def test_valid_cookie(dclient, conv_hash, url):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    ts = parse_datetime(obj[0].pop('ts'))
    assert 0 < (datetime.now() - ts).total_seconds() < 1
    obj[0].pop('id')
    assert [{'hash': conv_hash, 'subject': 'Test Conversation'}] == obj


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


async def test_list_details_conv(dclient, conv_hash, url):
    r = await dclient.get(url('list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['hash'] == conv_hash
    r = await dclient.get(url('get', conv=conv_hash))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['subject'] == 'Test Conversation'
    # TODO assert obj['messages'][0]['body'] == 'hello'


async def test_missing_conv(dclient, conv_hash, url):
    r = await dclient.get(url('get', conv=conv_hash + 'x'))
    assert r.status == 404, await r.text()
    text = await r.text()
    assert text.endswith('x not found')


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


async def test_add_message(dclient, conv_hash, url):
    data = {
        'subject': 'Test Subject',
        'message_follows': 'testkey_length16'
    }
    url_ = url('act', conv=conv_hash, component=Components.MESSAGE, verb=Verbs.ADD)
    r = await dclient.post(url_, json=data)
    assert r.status == 201, await r.text()
    obj = await r.json()
    print(obj)
