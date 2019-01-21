import base64
import logging
import os
from datetime import datetime
from textwrap import wrap

from aiohttp.web_exceptions import HTTPForbidden
from arq import RedisMixin
from arq.jobs import DatetimeJob
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from .. import Settings
from ..exceptions import FailedInboundAuthentication
from ..utils.encoding import to_unix_ms
from .dns import DNSResolver

logger = logging.getLogger('em2.f.auth')


class Authenticator(RedisMixin):
    job_class = DatetimeJob
    _dft_value = b'1'

    def __init__(self, settings: Settings, *, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        self.redis_settings = self.settings.redis
        super().__init__(**kwargs)
        self._resolver = None
        self._past_ts_limit, self._future_ts_limit = self.settings.COMMS_AUTHENTICATION_TS_LENIENCY
        self._token_length = self.settings.COMMS_PLATFORM_TOKEN_LENGTH
        self.dns = DNSResolver(self.settings, self.loop)

    async def authenticate_platform(self, platform: str, timestamp: int, signature: str):
        """
        Check a request is "from" a domain by asserting that the signature of the supplied string is valid.
        :param platform: domain of platform being authenticated
        :param timestamp: unix timestamp in seconds, must be close to now
        :param signature: signature of platform_timestamp
        :return: new API token for the platform which is valid for COMMS_PLATFORM_TOKEN_TIMEOUT
        """

        now = self._now_unix()
        l_limit, u_limit = now + self._past_ts_limit, now + self._future_ts_limit
        if not l_limit < timestamp < u_limit:
            raise FailedInboundAuthentication('{} was not between {} and {}'.format(timestamp, l_limit, u_limit))

        public_key = await self.get_public_key(platform)
        signed_message = '{}:{}'.format(platform, timestamp)
        if not self.valid_signature(signed_message, signature, public_key):
            raise FailedInboundAuthentication('invalid signature')
        token_expires_at = now + self.settings.COMMS_PLATFORM_TOKEN_TIMEOUT
        platform_token = '{}:{}:{}'.format(platform, token_expires_at, self._generate_random())
        await self._store_platform_token(platform_token, token_expires_at)
        return platform_token

    async def validate_platform_token(self, token):
        if not await self.redis.exists(token.encode()):
            raise HTTPForbidden(text='invalid token')
        return token.split(':', 1)[0]

    async def check_domain_platform(self, domain, platform):
        if not await self._check_domain_uses_platform(domain, platform):
            raise HTTPForbidden(text=f'"{domain}" does not use "{platform}"')

    async def get_public_key(self, platform: str):
        dns_results = await self.dns.query(platform, 'TXT')
        logger.info('got %d TXT records for %s', len(dns_results), platform)
        key_data = self._get_public_key_from_dns(dns_results)
        # return the key in a format openssl / RSA.importKey can cope with
        return '-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n'.format('\n'.join(wrap(key_data, width=64)))

    @classmethod
    def _get_public_key_from_dns(cls, dns_results: tuple):
        results = (r.text.decode() for r in dns_results)
        for r in results:
            if r.lower().startswith('v=em2key'):
                # [8:] removes the "v=em2key"
                key = r[8:].strip()
                if key.endswith('='):
                    return key
                else:
                    # https://tools.ietf.org/html/rfc4408#section-3.1.3
                    # this could be the wrong interpretation, the above case could suffice
                    for extra in results:
                        key += extra.strip()
                        if extra.endswith('='):
                            # key finished
                            return key
        raise FailedInboundAuthentication('no "em2key" TXT dns record found')

    async def _store_platform_token(self, token: str, expires_at: int):
        redis = await self.get_redis()
        pipe = redis.pipeline()
        key = token.encode()
        pipe.set(key, self._dft_value)
        pipe.expireat(key, expires_at)
        await pipe.execute()

    async def _check_domain_uses_platform(self, domain: str, platform_domain: str):
        cache_key = b'pl:%s' % domain.encode()
        redis = await self.get_redis()
        cache_p = await redis.get(cache_key)
        if cache_p and cache_p.decode() == platform_domain:
            return True
        async for host in self.dns.mx_hosts(domain):
            if host == platform_domain:
                await self.redis.setex(cache_key, self.settings.COMMS_DOMAIN_CACHE_TIMEOUT, host.encode())
                return True

    def valid_signature(self, signed_message, signature, public_key):
        try:
            key = RSA.importKey(public_key)
        except ValueError as e:
            raise FailedInboundAuthentication(*e.args) from e

        # signature needs to be decoded from base64
        signature = base64.urlsafe_b64decode(signature)

        h = SHA256.new(signed_message.encode())
        cipher = PKCS1_v1_5.new(key)
        return cipher.verify(h, signature)

    def _now_unix(self):
        return to_unix_ms(datetime.utcnow())

    def _generate_random(self):
        return base64.urlsafe_b64encode(os.urandom(self._token_length))[:self._token_length].decode()
