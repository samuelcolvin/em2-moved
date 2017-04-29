import base64

from cryptography.fernet import Fernet

from em2.core import Action, Verbs
from em2.utils import msg_encode
from tests.fixture_classes.push import create_test_app


async def test_list_single_conversation(test_client, reset_store):
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
    r = await client.get('/ui/list/')
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert len(obj) == 1
    assert obj[0]['conv_id'] == conv_id
