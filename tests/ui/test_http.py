import base64

from cryptography.fernet import Fernet

from em2.core import Action, Verbs
from em2.utils import msg_encode
from tests.fixture_classes.push import create_test_app


async def test_list_single_conversation(test_client, reset_store):
    # builds test setup without custom fixtures for demo purposes
    data = {'address': 'testing@example.com'}
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(b'i am not secure but 32 bits long'))
    cookies = {
        'em2session': fernet.encrypt(data).decode()
    }
    client = await test_client(create_test_app(), cookies=cookies)
    ctrl = client.server.app['controller']
    action = Action('testing@example.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar', body='hi, how are you?')
    r = await client.get(client.server.app['uiapp'].router['retrieve-list'].url_for())
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert len(obj) == 1
    assert obj[0]['conv_id'] == conv_id


async def test_no_cookie(client, conv_id, url):
    client.session.cookie_jar.clear()
    r = await client.get(url('retrieve-list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_invalid_cookie(client, conv_id, url):
    data = {'address': 'testing@example.com'}
    data = msg_encode(data)
    fernet = Fernet(base64.urlsafe_b64encode(b'i am different and 32 bits long!'))
    settings = client.server.app['settings']
    cookies = {settings.COOKIE_NAME: fernet.encrypt(data).decode()}
    client.session.cookie_jar.update_cookies(cookies)
    r = await client.get(url('retrieve-list'))
    assert r.status == 403, await r.text()
    assert 'Invalid token' in await r.text()


async def test_list_details_conv(client, conv_id, url):
    r = await client.get(url('retrieve-list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[0]['conv_id'] == conv_id
    r = await client.get(url('retrieve-conv', conv=conv_id))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj['messages'][0]['body'] == 'hello'


async def test_missing_conv(client, conv_id, url):
    r = await client.get(url('retrieve-conv', conv=conv_id + 'x'))
    assert r.status == 404, await r.text()
    text = await r.text()
    assert text.endswith('x not found')
