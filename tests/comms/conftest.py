import pytest

from em2 import Settings
from tests.fixture_classes import get_private_key_file
from tests.fixture_classes.push import HttpMockedDNSPusher


@pytest.yield_fixture
def get_pusher(loop, get_redis_pool):
    pusher = None

    async def _create_pusher():
        nonlocal pusher
        settings = Settings(
            DATASTORE_CLS='em2.ds.NullDataStore',
            PUSHER_CLS='tests.fixture_classes.push.HttpMockedDNSPusher',
            PRIVATE_DOMAIN_KEY_FILE=get_private_key_file(),
        )
        pusher = HttpMockedDNSPusher(settings, loop=loop, is_shadow=True)
        pusher._redis_pool = await get_redis_pool()
        await pusher.startup()
        return pusher

    yield _create_pusher
    if pusher:
        loop.run_until_complete(pusher.shutdown())
