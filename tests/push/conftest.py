import pytest
from aiohttp.web import Application, json_response

from em2.foreign import create_foreign_app
from tests.conftest import shutdown_modify_app, startup_modify_app
from tests.fixture_classes import DNSMockedPusher, create_test_app

test_addr = 'testing@example.com'


@pytest.fixture
def cli(loop, settings, db_conn, test_client, redis):
    app = create_foreign_app(settings)
    app['_conn'] = db_conn
    app.on_startup.append(startup_modify_app)
    app.on_shutdown.append(shutdown_modify_app)
    return loop.run_until_complete(test_client(app))


@pytest.fixture
def setup_check_server(loop, test_server):
    app = Application()

    async def _mock_index(request):
        return json_response({'domain': f'127.0.0.1:{server.port}'})

    app.router.add_get('/', _mock_index)

    server = loop.run_until_complete(test_server(app))
    return server


@pytest.fixture()
def foreign_server(loop, test_server):
    app = create_test_app(loop)

    return loop.run_until_complete(test_server(app))


@pytest.yield_fixture
def mocked_pusher(loop, settings, db_conn, foreign_server):
    async def _init():
        _pusher = DNSMockedPusher(settings, loop=loop, worker=True)
        await _pusher.startup()
        _pusher.db.conn = db_conn

        _pusher.set_foreign_port(foreign_server.port)
        return _pusher

    pusher = loop.run_until_complete(_init())
    yield pusher
    loop.run_until_complete(pusher.close(shutdown=True))


@pytest.fixture
def conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator=test_addr, published=True))


@pytest.fixture
def draft_conv(loop, create_conv):
    return loop.run_until_complete(create_conv(creator=test_addr))
