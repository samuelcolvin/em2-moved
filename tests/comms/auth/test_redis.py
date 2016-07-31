import pytest

from em2 import Settings
from em2.comms import RedisDNSAuthenticator
from em2.exceptions import FailedAuthentication
from tests.fixture_classes import RedisMockDNSAuthenticator, PLATFORM, TIMESTAMP, VALID_SIGNATURE


@pytest.yield_fixture
def redis_auth(loop):
    settings = Settings(REDIS_DATABASE=2)
    auth = None

    async def flushdb():
        async with auth._redis_pool.get() as redis:
            await redis.flushdb()

    async def setup(auth_class=RedisDNSAuthenticator):
        nonlocal auth
        auth = auth_class(settings, loop=loop)
        await auth.get_redis_pool()
        await flushdb()
        return auth

    yield setup

    if auth:
        loop.run_until_complete(flushdb())
        loop.run_until_complete(auth.close())


async def test_key_set_get(redis_auth):
    auth = await redis_auth()
    expireat = auth._now_unix() + 100
    await auth._store_key('testing', expireat)
    assert await auth._platform_token_exists('testing') is True
    async with auth._redis_pool.get() as redis:
        assert 99 <= await redis.ttl('testing') <= 100


async def test_key_set_get_missing(redis_auth):
    auth = await redis_auth()
    assert await auth._platform_token_exists('other') is False


async def test_key_verification(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    platform_key = await auth.authenticate_platform(PLATFORM, TIMESTAMP, VALID_SIGNATURE)
    await auth.valid_platform_token(platform_key)


async def test_key_verification_missing_dns(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform('notfoobar.com', 2461449600, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'no "em2key" TXT dns record found'


async def test_key_verification_bad_em2key(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    auth._now_unix = lambda: 2461449600

    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform('badkey.com', 2461449600, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'no "em2key" TXT dns record found'


async def test_check_domain_platform_cache(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    assert await auth._check_domain_uses_platform('whatever.com', 'whoever.com') is None
    async with auth._redis_pool.get() as redis:
        await redis.set(b'pl:whatever.com', b'whoever.com')
    assert await auth._check_domain_uses_platform('whatever.com', 'whoever.com') is True


async def test_check_domain_platform_mx_match(redis_auth):
    auth = await redis_auth(RedisMockDNSAuthenticator)
    assert await auth._check_domain_uses_platform('whatever.com', 'ten.example.com') is True
    async with auth._redis_pool.get() as redis:
        await redis.get('pl:whatever.com') == 'ten.example.com'

async def test_mx_lookup(redis_auth):
    auth = await redis_auth()
    r = auth.resolver
    results = await r.query('gmail.com', 'MX')
    assert results[0].host.endswith('google.com')
    # check we get back the same resolver each time
    assert id(r) == id(auth._resolver)
