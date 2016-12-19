import pytest

from em2 import Settings
from tests.fixture_classes.authenicator import get_private_key
from tests.fixture_classes.push import HttpMockedDNSPusher


@pytest.yield_fixture
def get_pusher(loop, get_redis_pool):
    pusher = None

    async def _create_pusher():
        nonlocal pusher
        settings = Settings(
            PUSHER_CLS='tests.fixture_classes.push.HttpMockedDNSPusher',
            PRIVATE_DOMAIN_KEY=get_private_key(),
        )
        pusher = HttpMockedDNSPusher(settings, loop=loop, is_shadow=True)
        pusher._redis_pool = await get_redis_pool()
        return pusher

    yield _create_pusher
    if pusher:
        loop.run_until_complete(pusher.close())
