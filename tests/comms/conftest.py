import pytest

from em2 import Settings
from tests.fixture_classes.authenicator import get_private_key
from tests.fixture_classes.push import HttpMockedDNSPusher


@pytest.yield_fixture
def pusher(loop, redis_pool):
    settings = Settings(
        PUSHER_CLS='tests.fixture_classes.push.HttpMockedDNSPusher',
        PRIVATE_DOMAIN_KEY=get_private_key(),
    )
    pusher = HttpMockedDNSPusher(settings, loop=loop, is_shadow=True)
    pusher._redis_pool = redis_pool

    yield pusher
    loop.run_until_complete(pusher.close())
