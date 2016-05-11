from datetime import datetime

import pytest

from em2 import Settings
from em2.exceptions import PlatformForbidden
from tests.fixture_classes.simple_authenicator import SimpleAuthenticator


async def test_key_doesnt_exists():
    auth = SimpleAuthenticator(Settings(), None)
    with pytest.raises(PlatformForbidden):
        await auth.valid_platform_key('foobar.com:123:whatever')


async def test_key_does_exists():
    auth = SimpleAuthenticator(Settings(), None)
    auth.valid_signature_override = True

    # note: strftime('%s') has to be used with now() to avoid double tz conversion
    pt_ts = 'foobar.com:{:%s}'.format(datetime.now())

    platform_key = await auth.authenticate_platform(pt_ts, 'foobar')

    await auth.valid_platform_key(platform_key)
