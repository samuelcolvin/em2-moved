from pathlib import Path
from textwrap import wrap

from em2.comms.auth import BaseAuthenticator, RedisDNSAuthenticator

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


def get_private_key():
    with (KEY_DIR / 'private.pem').open() as f:
        return f.read()


class SimpleAuthenticator(BaseAuthenticator):
    def __init__(self, settings):
        super().__init__(settings)
        self._cache = {
            'already-authenticated.com:123:whatever': 2461449700
        }
        self.public_key_value = get_public_key()
        self.valid_signature_override = None

    async def key_exists(self, platform_key):
        exp = self._cache.get(platform_key, 1)
        return exp > self._now_unix()

    async def _get_public_key(self, platform):
        return self.public_key_value

    async def _store_platform_token(self, key, expires_at):
        self._cache[key] = expires_at

    async def _check_domain_uses_platform(self, domain, platform_domain):
        return platform_domain.endswith(domain)

    def _valid_signature(self, signed_message, signature, public_key):
        if isinstance(self.valid_signature_override, bool):
            return self.valid_signature_override
        return super()._valid_signature(signed_message, signature, public_key)


class TXTQueryResult:
    def __init__(self, text):
        self.text = text


class MXQueryResult:
    def __init__(self, priority, host):
        self.priority = priority
        self.host = host


class MockDNSResolver:
    async def query(self, host, qtype):
        if qtype == 'TXT':
            return self.get_txt(host)
        elif qtype == 'MX':
            return self.get_mx(host)
        else:
            return self.get_other(host, qtype)

    def get_txt(self, host):
        r = [TXTQueryResult('v=spf1 include:spf.example.com ?all')]
        if host == 'foobar.com':
            public_key = get_public_key()
            public_key = public_key.replace('-----BEGIN PUBLIC KEY-----', '')
            public_key = public_key.replace('-----END PUBLIC KEY-----', '').replace('\n', '')
            rows = wrap(public_key, width=250)
            rows[0] = 'v=em2key p=' + rows[0]
            r += [TXTQueryResult(t) for t in rows]
        elif host == 'badkey.com':
            r += [
                TXTQueryResult('v=em2key p=123'),
                TXTQueryResult('456'),
                TXTQueryResult('789'),
            ]
        r.append(TXTQueryResult('v=foobar'))
        return r

    def get_mx(self, host):
        if host == 'local.com':
            return [
                MXQueryResult(5, 'em2.local.com'),
                MXQueryResult(10, 'mx.local.com'),
            ]
        elif host == 'nomx.com':
            return []
        else:
            return [
                MXQueryResult(10, 'mx.platform.' + host),
                MXQueryResult(5, 'em2.platform.' + host),
            ]

    def get_other(self, host, qtype):
        raise NotImplemented()


class RedisMockDNSAuthenticator(RedisDNSAuthenticator):
    @property
    def resolver(self):
        return MockDNSResolver()
