from em2.foreign.auth import Authenticator
from em2.push import Pusher
from tests.fixture_classes import DNSMockedPusher


async def test_setup_check_pass(settings, loop, setup_check_server):
    settings.EXTERNAL_DOMAIN = f'127.0.0.1:{setup_check_server.port}'
    pusher = DNSMockedPusher(settings, loop=loop, worker=True)
    await pusher.startup()
    try:
        http_pass, dns_pass = await pusher.setup_check.direct()
        assert http_pass
        assert dns_pass
    finally:
        await pusher.shutdown()


async def test_setup_check_fail(settings, loop, foreign_server):
    settings = settings.copy(update={
        'EXTERNAL_DOMAIN': f'localhost:{foreign_server.port}/status/400',
        'authenticator_cls': Authenticator,
    })
    pusher = Pusher(settings, loop=loop, worker=True)
    await pusher.startup()
    http_pass, dns_pass = await pusher.setup_check.direct(_retry_delay=0.01)
    assert http_pass is False
    assert dns_pass is False

    await pusher.shutdown()


async def test_setup_check_fail_client_error(settings, loop):
    settings = settings.copy(update={
        'EXTERNAL_DOMAIN': f'localhost:123456',
        'authenticator_cls': Authenticator,
    })
    pusher = Pusher(settings, loop=loop, worker=True)
    await pusher.startup()
    http_pass, dns_pass = await pusher.setup_check.direct(_retry_delay=0.01)
    assert http_pass is False
    assert dns_pass is False

    await pusher.shutdown()
