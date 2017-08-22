from pathlib import Path
from textwrap import wrap
from typing import NamedTuple

from aiodns.error import DNSError

# from em2.comms.auth import BaseAuthenticator, RedisDNSAuthenticator
from em2.foreign.auth import Authenticator

# to generate public and private keys
# openssl genrsa -out private.pem 4096
# openssl rsa -in private.pem -pubout > public.pem

KEY_DIR = (Path(__file__).parent / 'keys').absolute()

# printf 'foobar.com:2461449600' > test.txt
# openssl dgst -sha256 -sign tests/fixture_classes/keys/private.pem -out test.sig test.txt
# python -c "import base64; print(base64.urlsafe_b64encode(open('test.sig', 'rb').read()).decode())"
PLATFORM = 'foobar.com'
TIMESTAMP = 2461449600
VALID_SIGNATURE = (
    'hzr-wL7mFQcTymT1xnF1cTgWTL-8Sxc_AJejZiARXFjGcLbOW32bnSjYAKMa-vPdQlB0G2Vz8FJQ2kNzsV12G15LIjb-8FyaPoF0Axman'
    'U_gYzShZMQSpPyt9kP8x7VwKFe3DdExJBlWgVw0gB_O5fh6SZ7RppkMiXlZoS3OXT1y4x1ZmTqwFcZZARfeSZa2BK3kJ2xbyHn9CdXh88'
    'iFwYLh_eMWcaOgTYOw4YWsX9EktUZUTdknJfjLr_5mK-jiHNvVfjS11PdImHMQGu7MhkkQiXbmjFzgYNoS5_phdSB8UGkkCVJ-txm2JEI'
    'aZZ-Q-yl19hEoHqg-PhEVi30tdAyGifldSZfbT8gxk2laer__unGJQF_WB46UiKTgxJODh9hNRM4e-9opwH5MLX7nNPLsFa3QjfY9EJb9'
    'OHqFfmEtWM8-aqhf-3HHBxLfjvTm9ZdH-zbesnSb6NbdY8BOWK6G2iVQQbH2YAQN_QjNvoZedI7ZQCZeuHm9XjRpi1ECLn8jjN8PtIJ84'
    'eYYbgI0b6gcFkB0YBJcM59MNGYkdJkJtfQI-EHqPaSByrFEMME3RerbjePMSVHoBlbpKgFRGNzAgFX0s3zbIxA-0g25skMAY_mIS_XWQE'
    '3JnlcZOSIyrff4LcU_ZEwIOxdKKWkPIq6oZKXfM8fsXz4yA7vY9K0='
)


def get_public_key():
    with (KEY_DIR / 'public.pem').open() as f:
        return f.read()


def get_private_key_file():
    return str(KEY_DIR / 'private.pem')


class SimpleAuthenticator(Authenticator):
    def __init__(self, settings, **kwargs):
        super().__init__(settings, **kwargs)
        self.key_added = False
        self.public_key_value = get_public_key()
        self.valid_signature_override = None

    async def _set_key(self):
        if not self.key_added:
            self.key_added = True
            async with await self.get_redis_conn() as redis:
                await redis.set('already-authenticated.com:123:whatever', 2461449700)

    async def validate_platform_token(self, token):
        # set the dummy key on the first validation
        await self._set_key()
        return await super().validate_platform_token(token)

    async def _get_public_key(self, platform):
        return self.public_key_value

    async def _check_domain_uses_platform(self, domain, platform_domain):
        return platform_domain.endswith(domain)

    def _valid_signature(self, signed_message, signature, public_key):
        if isinstance(self.valid_signature_override, bool):
            return self.valid_signature_override
        return super()._valid_signature(signed_message, signature, public_key)

    def _now_unix(self):
        return TIMESTAMP


class DnsMockAuthenticator(Authenticator):
    @property
    def resolver(self):
        return MockDNSResolver()


class FixedDnsMockAuthenticator(DnsMockAuthenticator):
    def _now_unix(self):
        return 2461449600


class TXTQueryResult(NamedTuple):
    text: bytes


class MXQueryResult(NamedTuple):
    priority: int
    host: str


class MockDNSResolver:
    def __init__(self, port=0):
        self._port = port

    async def query(self, host, qtype):
        if qtype == 'TXT':
            return self.get_txt(host)
        elif qtype == 'MX':
            return self.get_mx(host)
        else:
            return self.get_other(host, qtype)

    def get_txt(self, host):
        r = [TXTQueryResult(text=b'v=spf1 include:spf.example.com ?all')]
        if host == 'foobar.com':
            public_key = get_public_key()
            public_key = public_key.replace('-----BEGIN PUBLIC KEY-----', '')
            public_key = public_key.replace('-----END PUBLIC KEY-----', '').replace('\n', '')
            rows = wrap(public_key, width=250)
            rows[0] = 'v=em2key ' + rows[0]
            r += [TXTQueryResult(text=t.encode()) for t in rows]
        elif host == 'badkey1.com':
            r += [
                TXTQueryResult(text=b'v=em2key 123'),
                TXTQueryResult(text=b'456'),
                TXTQueryResult(text=b'789'),
            ]
        elif host == 'badkey2.com':
            r += [
                TXTQueryResult(text=b'v=em2key 123'),
                TXTQueryResult(text=b'456'),
                TXTQueryResult(text=b'789='),
            ]
        r.append(TXTQueryResult(text=b'v=foobar'))
        return r

    def get_mx(self, host):
        if host == 'local.com':
            return [
                MXQueryResult(5, f'em2.platform.example.com:{self._port}'),
                MXQueryResult(10, f'mx.platform.example.com:{self._port}'),
            ]
        elif host == 'nomx.com':
            return []
        elif host == 'value_error.com':
            raise ValueError('DNS error with error.com')
        elif host == 'dns_error.com':
            raise DNSError('snap')
        if host == 'fallback.com':
            return [
                MXQueryResult(priority=10, host='mx.local.com'),
            ]
        else:
            extra = f':{self._port}' if self._port else ''
            return [
                MXQueryResult(priority=10, host=f'mx.platform.{host}{extra}'),
                MXQueryResult(priority=5, host=f'em2.platform.{host}{extra}'),
            ]

    def get_other(self, host, qtype):
        raise NotImplemented()
