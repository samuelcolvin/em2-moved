
import pytest
from aiohttp.web_exceptions import HTTPForbidden

from em2.exceptions import FailedInboundAuthentication
from em2.foreign.auth import Authenticator
from em2.push import Pusher
from tests.fixture_classes import DNSMockedPusher
from tests.fixture_classes.auth import TIMESTAMP, DnsMockAuthenticator, FixedDnsMockAuthenticator, get_public_key
from tests.fixture_classes.dns_resolver import VALID_SIGNATURE


async def test_valid_public_key(settings, loop, redis):
    auth = FixedDnsMockAuthenticator(settings, loop=loop)
    token = await auth.authenticate_platform('foobar.com', TIMESTAMP, VALID_SIGNATURE)
    await auth.close()
    print(token)
    assert token.startswith('foobar.com:2461536000:')


async def test_bad_key(settings, loop, redis):
    auth = FixedDnsMockAuthenticator(settings, loop=loop)
    with pytest.raises(FailedInboundAuthentication) as exc_info:
        await auth.authenticate_platform('badkey1.com', TIMESTAMP, VALID_SIGNATURE)
    await auth.close()
    assert exc_info.value.text == 'Authenticate failed: no "em2key" TXT dns record found'


async def test_invalid_key(settings, loop, redis):
    auth = FixedDnsMockAuthenticator(settings, loop=loop)
    with pytest.raises(FailedInboundAuthentication) as exc_info:
        await auth.authenticate_platform('badkey2.com', TIMESTAMP, VALID_SIGNATURE)
    await auth.close()
    assert exc_info.value.text.startswith('Authenticate failed: ')


async def test_timstamp_wrong(settings, loop, redis):
    auth = DnsMockAuthenticator(settings, loop=loop)
    with pytest.raises(FailedInboundAuthentication) as exc_info:
        await auth.authenticate_platform('foobar.com', TIMESTAMP - 100, VALID_SIGNATURE)
    await auth.close()
    assert 'was not between' in exc_info.value.text


async def test_real_valid_public_key(settings, loop, redis):
    auth = Authenticator(settings, loop=loop)
    key = await auth.get_public_key('unittest.imber.io')
    assert key == get_public_key()
    # repeat check
    key = await auth.get_public_key('unittest.imber.io')
    await auth.close()
    assert key == get_public_key()


async def test_real_no_public_key(settings, loop, redis):
    auth = Authenticator(settings, loop=loop)
    with pytest.raises(FailedInboundAuthentication) as exc_info:
        await auth.get_public_key('example.com')
    await auth.close()
    assert exc_info.value.text == 'Authenticate failed: no "em2key" TXT dns record found'


async def test_real_domain_does_not_exists(settings, loop, redis):
    auth = Authenticator(settings, loop=loop)
    with pytest.raises(FailedInboundAuthentication) as exc_info:
        await auth.get_public_key('doesnotexist.example.com')
    await auth.close()
    assert exc_info.value.text == 'Authenticate failed: no "em2key" TXT dns record found'


async def test_domain_uses_true(mocker, settings, loop, redis):
    auth = DnsMockAuthenticator(settings, loop=loop)
    mocker.spy(auth.dns, 'mx_hosts')
    await auth.check_domain_platform('local.com', 'em2.platform.example.com:0')
    await auth.check_domain_platform('local.com', 'em2.platform.example.com:0')
    await auth.check_domain_platform('local.com', 'em2.platform.example.com:0')
    await auth.close()
    assert auth.dns.mx_hosts.call_count == 1


async def test_domain_uses_false(mocker, settings, loop, redis):
    auth = DnsMockAuthenticator(settings, loop=loop)
    mocker.spy(auth.dns, 'mx_hosts')
    with pytest.raises(HTTPForbidden):
        await auth.check_domain_platform('local.com', 'other.com')
    await auth._check_domain_uses_platform('local.com', 'other.com')
    await auth._check_domain_uses_platform('local.com', 'other.com')
    await auth.close()
    assert auth.dns.mx_hosts.call_count == 3


async def test_setup_check_pass(settings, loop, cli):
    original_external = cli.server.app['settings'].EXTERNAL_DOMAIN
    pusher = DNSMockedPusher(settings, loop=loop, worker=True)
    await pusher.startup()
    pusher.set_foreign_port(cli.server.port)
    cli.server.app['settings'].EXTERNAL_DOMAIN = f'{original_external}:{cli.server.port}'
    http_pass, dns_pass = await pusher.setup_check.direct()
    assert http_pass
    assert dns_pass

    await pusher.shutdown()
    cli.server.app['settings'].EXTERNAL_DOMAIN = original_external


async def test_setup_check_fail(settings, loop, foreign_server):
    settings = settings.copy(update={
        'EXTERNAL_DOMAIN': f'localhost:{foreign_server.port}/status/503',
        'authenticator_cls': Authenticator,
    })
    pusher = Pusher(settings, loop=loop, worker=True)
    await pusher.startup()
    http_pass, dns_pass = await pusher.setup_check.direct(_retry_delay=0.01)
    assert http_pass is False
    assert dns_pass is False

    await pusher.shutdown()
