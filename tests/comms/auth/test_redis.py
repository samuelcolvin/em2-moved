import pytest

from em2 import Settings
from em2.comms import RedisDNSAuthenticator


@pytest.yield_fixture
def redis_auth(loop):
    settings = Settings(REDIS_DATABASE=2)
    auth = RedisDNSAuthenticator(settings, loop=loop)
    async def flushdb(_auth):
        async with _auth._redis_pool.get() as redis:
            await redis.flushdb()

    loop.run_until_complete(auth.init())
    loop.run_until_complete(flushdb(auth))

    yield auth

    loop.run_until_complete(flushdb(auth))
    loop.run_until_complete(auth.finish())


async def test_key_set_get(redis_auth):
    expireat = redis_auth._now_unix() + 100
    await redis_auth._store_key('testing', expireat)
    assert await redis_auth._platform_key_exists('testing') is True
    async with redis_auth._redis_pool.get() as redis:
        assert 99 <= await redis.ttl('testing') <= 100


async def test_key_set_get_missing(redis_auth):
    assert await redis_auth._platform_key_exists('other') is False
