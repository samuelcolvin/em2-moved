import pytest

from em2 import Settings
from em2.core import Controller
from tests.fixture_classes import get_private_key_file
from tests.fixture_classes.push import DoubleMockPusher, create_test_app


@pytest.fixture
def client(loop, test_client, reset_store):
    test_client = loop.run_until_complete(test_client(create_test_app))
    test_client.em2_ctrl = test_client.server.app['controller']
    return test_client


@pytest.yield_fixture
def ctrl_pusher(loop, reset_store):
    _pusher, _ctrl = None, None

    async def _create():
        nonlocal _pusher, _ctrl
        settings = Settings(
            R_DATABASE=2,
            LOCAL_DOMAIN='em2.local.com',
            PRIVATE_DOMAIN_KEY_FILE=get_private_key_file(),
            DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
            PUSHER_CLS='tests.fixture_classes.push.DoubleMockPusher',
        )
        _ctrl = Controller(settings, loop=loop)
        _pusher = DoubleMockPusher(settings, loop=loop, is_shadow=True)
        await _pusher.startup()
        await _pusher.create_test_client()
        async with await _pusher.get_redis_conn() as redis:
            await redis.flushall()
        return _ctrl, _pusher

    yield _create

    async def close():
        _pusher.test_client and await _pusher.test_client.close()
        await _pusher.shutdown()
        await _ctrl.pusher.shutdown()

    loop.run_until_complete(close())
