from em2 import Settings
from em2.utils import now_unix_timestamp


async def test_authenticate(domain_pusher):
    pusher = await domain_pusher('example.com')
    token = await pusher.authenticate('example.com')
    assert token.startswith('em2.local.com:2461536000:')
    async with pusher._redis_pool.get() as redis:
        v = await redis.get(b'ak:example.com')
        assert token == v.decode()
        ttl = await redis.ttl(b'ak:example.com')
        expiry = ttl + now_unix_timestamp()
        expected_expiry = 2461536000 - Settings().COMMS_PUSH_TOKEN_EARLY_EXPIRY
        assert abs(expiry - expected_expiry) < 10


async def test_get_node_local(domain_pusher):
    pusher = await domain_pusher('four.example.com')
    r = await pusher.get_node('123', 'local.com')
    assert r == pusher.LOCAL


async def test_get_node_remote(domain_pusher):
    pusher = await domain_pusher('four.example.com')
    r = await pusher.get_node('123', 'example.com')
    assert r == 'em2.four.example.com'
