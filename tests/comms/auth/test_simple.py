from datetime import datetime

import pytest

from em2.exceptions import PlatformForbidden, FailedAuthentication, DomainPlatformMismatch
from tests.fixture_classes.simple_authenicator import SimpleAuthenticator


# printf 'foobar.com:2461449600' > test2.txt
# openssl dgst -sha256 -sign tests/fixture_classes/keys/private.pem -out test.sig test.txt
# python -c "import base64; print(base64.urlsafe_b64encode(open('test.sig', 'rb').read()).decode('utf8'))"
PLATFORM_TIMESTAMP = 'foobar.com:2461449600'
VALID_SIGNATURE = (
    'hzr-wL7mFQcTymT1xnF1cTgWTL-8Sxc_AJejZiARXFjGcLbOW32bnSjYAKMa-vPdQlB0G2Vz8FJQ2kNzsV12G15LIjb-8FyaPoF0Axman'
    'U_gYzShZMQSpPyt9kP8x7VwKFe3DdExJBlWgVw0gB_O5fh6SZ7RppkMiXlZoS3OXT1y4x1ZmTqwFcZZARfeSZa2BK3kJ2xbyHn9CdXh88'
    'iFwYLh_eMWcaOgTYOw4YWsX9EktUZUTdknJfjLr_5mK-jiHNvVfjS11PdImHMQGu7MhkkQiXbmjFzgYNoS5_phdSB8UGkkCVJ-txm2JEI'
    'aZZ-Q-yl19hEoHqg-PhEVi30tdAyGifldSZfbT8gxk2laer__unGJQF_WB46UiKTgxJODh9hNRM4e-9opwH5MLX7nNPLsFa3QjfY9EJb9'
    'OHqFfmEtWM8-aqhf-3HHBxLfjvTm9ZdH-zbesnSb6NbdY8BOWK6G2iVQQbH2YAQN_QjNvoZedI7ZQCZeuHm9XjRpi1ECLn8jjN8PtIJ84'
    'eYYbgI0b6gcFkB0YBJcM59MNGYkdJkJtfQI-EHqPaSByrFEMME3RerbjePMSVHoBlbpKgFRGNzAgFX0s3zbIxA-0g25skMAY_mIS_XWQE'
    '3JnlcZOSIyrff4LcU_ZEwIOxdKKWkPIq6oZKXfM8fsXz4yA7vY9K0='
)


async def test_key_doesnt_exists():
    auth = SimpleAuthenticator()
    with pytest.raises(PlatformForbidden):
        await auth.valid_platform_key('foobar.com:123:whatever')


async def test_key_does_exists():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True

    # note: strftime('%s') has to be used with now() to avoid double tz conversion
    n = int(datetime.now().strftime('%s'))
    pt_ts = 'foobar.com:{}'.format(n)

    platform_key = await auth.authenticate_platform(pt_ts, 'foobar')
    platform, exp, rand = platform_key.split(':', 2)
    assert platform == 'foobar.com'
    assert 86390 < (int(exp) - n) < 86410
    assert len(rand) == 64

    await auth.valid_platform_key(platform_key)

async def test_key_verification():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: 2461449600

    platform_key = await auth.authenticate_platform(PLATFORM_TIMESTAMP, VALID_SIGNATURE)
    await auth.valid_platform_key(platform_key)


async def test_key_verification_bad_signature():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: 2461449600
    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform(PLATFORM_TIMESTAMP, VALID_SIGNATURE.replace('2', '3'))
    assert excinfo.value.args[0] == 'invalid signature'


async def test_key_verification_bad_ts():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: 2461449600
    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform('foobar.com:246144X9600', VALID_SIGNATURE)
    assert excinfo.value.args[0] == '"246144X9600" is not a valid timestamp'


async def test_key_verification_old_ts():
    auth = SimpleAuthenticator()
    auth._now_unix = lambda: 2461449600
    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform('foobar.com:2461449100', VALID_SIGNATURE)
    assert excinfo.value.args[0] == '2461449100 was not between 2461449590 and 2461449601'


async def test_invalid_public_key():
    auth = SimpleAuthenticator()
    auth.public_key_value = 'whatever'
    auth._now_unix = lambda: 2461449600

    with pytest.raises(FailedAuthentication) as excinfo:
        await auth.authenticate_platform(PLATFORM_TIMESTAMP, VALID_SIGNATURE)
    assert excinfo.value.args[0] == 'RSA key format is not supported'


async def test_check_domain():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True
    pt_ts = 'testing.foobar.com:{:%s}'.format(datetime.now())
    platform_key = await auth.authenticate_platform(pt_ts, 'anything')
    await auth.valid_platform_key(platform_key)
    await auth.check_domain('foobar.com', platform_key)


async def test_check_domain_missing():
    auth = SimpleAuthenticator()
    auth.valid_signature_override = True
    pt_ts = 'testing.foobar.com:{:%s}'.format(datetime.now())
    platform_key = await auth.authenticate_platform(pt_ts, 'anything')
    await auth.valid_platform_key(platform_key)
    with pytest.raises(DomainPlatformMismatch) as excinfo:
        await auth.check_domain('bang.com', platform_key)
    assert excinfo.value.args[0] == '"bang.com" does not use "testing.foobar.com"'
