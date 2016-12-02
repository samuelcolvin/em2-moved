from datetime import datetime

import pytest

from em2.exceptions import DomainPlatformMismatch, FailedInboundAuthentication, PlatformForbidden
from tests.fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE, SimpleAuthenticator


TS = 2461449600


async def test_key_doesnt_exists():
    auth = SimpleAuthenticator()
    with pytest.raises(PlatformForbidden):
        await auth.valid_platform_token('foobar.com:123:whatever')


async def test_key_does_exists():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True

    # note: strftime('%s') has to be used with now() to avoid double tz conversion
    n = int(datetime.now().strftime('%s'))

    platform_key = await auth.authenticate_platform('foobar.com', n, 'foobar')
    platform, exp, rand = platform_key.split(':', 2)
    assert platform == 'foobar.com'
    assert 86390 < (int(exp) - n) < 86410
    assert len(rand) == 64

    await auth.valid_platform_token(platform_key)


async def test_key_verification():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: TS

    platform_key = await auth.authenticate_platform(PLATFORM, TIMESTAMP, VALID_SIGNATURE)
    await auth.valid_platform_token(platform_key)


async def test_key_verification_bad_signature():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: TS
    with pytest.raises(FailedInboundAuthentication) as excinfo:
        await auth.authenticate_platform(PLATFORM, TIMESTAMP, VALID_SIGNATURE.replace('2', '3'))
    assert excinfo.value.args[0] == 'invalid signature'


async def test_key_verification_old_ts():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: TS
    with pytest.raises(FailedInboundAuthentication) as excinfo:
        await auth.authenticate_platform('foobar.com', 2461449100, VALID_SIGNATURE)
    assert excinfo.value.args[0] == '2461449100 was not between 2461449590 and 2461449601'


async def test_invalid_public_key():
    auth = SimpleAuthenticator()
    auth.public_key_value = 'whatever'
    auth._now_unix = lambda: TS

    with pytest.raises(FailedInboundAuthentication) as excinfo:
        await auth.authenticate_platform(PLATFORM, TIMESTAMP, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'RSA key format is not supported'


async def test_check_domain():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True
    ts = int(datetime.now().strftime('%s'))
    platform_token = await auth.authenticate_platform('testing.foobar.com', ts, 'anything')
    domain = await auth.valid_platform_token(platform_token)
    await auth.check_domain_platform('foobar.com', domain)


async def test_check_domain_missing():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True
    ts = int(datetime.now().strftime('%s'))
    platform_token = await auth.authenticate_platform('testing.foobar.com', ts, 'anything')
    token = await auth.valid_platform_token(platform_token)
    with pytest.raises(DomainPlatformMismatch) as excinfo:
        await auth.check_domain_platform('bang.com', token)
    assert excinfo.value.args[0] == '"bang.com" does not use "testing.foobar.com"'
