import pytest

from em2 import Settings
from tests.fixture_classes.push import HttpMockedDNSPusher

# TODO perhaps move this to http or delete if it's not going to get more tests


@pytest.yield_fixture
def pusher(redis_pool, loop):
    settings = Settings(R_DATABASE=2)

    async def setup(push_class=HttpMockedDNSPusher):
        _pusher = push_class(settings=settings, loop=loop, is_shadow=True)
        _pusher._redis_pool = redis_pool
        await _pusher.ainit()
        return _pusher

    _pusher = loop.run_until_complete(setup())

    yield _pusher


async def test_get_nodes_not_existing(loop, pusher):
    await pusher.get_nodes('foo@nomx.com')
    await pusher.get_nodes('foo@nomx.com')
    async with await pusher.get_redis_conn() as redis:
        node = await redis.get(b'dn:nomx.com')
        assert node == b'F'


async def test_save_nodes_existing(loop, pusher):
    async with await pusher.get_redis_conn() as redis:
        await redis.set(b'dn:nomx.com', b'somethingelse.com')
    await pusher.get_nodes('foo@nomx.com')
    async with await pusher.get_redis_conn() as redis:
        node = await redis.get(b'dn:nomx.com')
        assert node == b'somethingelse.com'
