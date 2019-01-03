import bcrypt
import pytest
from aiohttp.web import Application, json_response
from cryptography.fernet import Fernet

from em2.auth import create_auth_app
from em2.utils.encoding import msg_encode

TEST_ADDRESS = 'testing@example.com'
TEST_PASSWORD = 'valid-testing-password'


@pytest.fixture
async def cli(loop, auth_settings, auth_db_conn, aiohttp_client, auth_redis):
    app = create_auth_app(auth_settings)
    app['settings']._test_conn = auth_db_conn
    return await aiohttp_client(app)


@pytest.fixture
def inv_token(settings):
    def _token(address=TEST_ADDRESS, **kwargs):
        fernet = Fernet(settings.auth_invitation_secret)
        data = msg_encode(dict(address=address, **kwargs))
        return fernet.encrypt(data).decode()
    return _token


@pytest.fixture
async def user(auth_settings, auth_db_conn, cli):
    hashb = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(auth_settings.auth_bcrypt_work_factor))
    sql = 'INSERT INTO auth_users (address, password_hash, node) SELECT $1, $2, id FROM auth_nodes LIMIT 1'
    await auth_db_conn.execute(sql, TEST_ADDRESS, hashb.decode())

    return TEST_ADDRESS, TEST_PASSWORD


@pytest.fixture
async def g_recaptcha_server(aiohttp_server, cli):
    app = Application()

    async def _mock_verify(request):
        data = await request.post()
        return json_response({'success': 'good' in data['response']})

    app.router.add_post('/mock_verify', _mock_verify)

    server = await aiohttp_server(app)
    cli.server.app['settings'].grecaptcha_url = f'http://localhost:{server.port}/mock_verify'
    return server


@pytest.fixture
async def authenticate(cli, url, inv_token):
    url_ = url('accept-invitation', query=dict(token=inv_token(last_name='testing')))
    r = await cli.post(url_, json={'password': 'thisissecure'})
    assert r.status == 201, await r.text()
    assert len(cli.session.cookie_jar) == 1


@pytest.fixture
def settings(auth_settings):
    return auth_settings
