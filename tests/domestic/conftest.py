from time import time

import pytest
from cryptography.fernet import Fernet

from em2.domestic import create_domestic_app

from ..conftest import shutdown_modify_app, startup_modify_app

test_addr = 'testing@example.com'


@pytest.fixture
def cli(loop, settings, db_conn, test_client, redis):
    fernet = Fernet(settings.auth_session_secret)
    data = f'123:{int(time()) + settings.cookie_grace_time}:{test_addr}'
    cookies = {
        settings.cookie_name: fernet.encrypt(data.encode()).decode()
    }
    app = create_domestic_app(settings, 'd-testing')
    app['_conn'] = db_conn
    app.on_startup.append(startup_modify_app)
    app.on_shutdown.append(shutdown_modify_app)
    return loop.run_until_complete(test_client(app, cookies=cookies))


@pytest.fixture
def extra_cli(loop, settings, test_client, cli):
    async def _create(address):
        fernet = Fernet(settings.auth_session_secret)
        data = f'{hash(address)}:{int(time()) + settings.cookie_grace_time}:{address}'
        cookies = {settings.cookie_name: fernet.encrypt(data.encode()).decode()}
        return await test_client(cli.server, cookies=cookies)
    return _create


@pytest.fixture
def conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator=test_addr))


@pytest.fixture
def post_create_conv(cli, url):
    async def _create(subject='Test Subject', message='this is a message', publish=False):
        data = {'subject': subject, 'message': message, 'publish': publish}
        r = await cli.post(url('create'), json=data)
        assert r.status == 201, await r.text()
        return (await r.json())['key']

    return _create
