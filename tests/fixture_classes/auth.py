from em2.foreign.auth import Authenticator

from .dns_resolver import TIMESTAMP, MockDNSResolver, get_public_key


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

    async def get_public_key(self, platform):
        return self.public_key_value

    async def _check_domain_uses_platform(self, domain, platform_domain):
        return platform_domain.endswith(domain)

    def valid_signature(self, signed_message, signature, public_key):
        if isinstance(self.valid_signature_override, bool):
            return self.valid_signature_override
        return super().valid_signature(signed_message, signature, public_key)

    def _now_unix(self):
        return TIMESTAMP


class DnsMockAuthenticator(Authenticator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dns = MockDNSResolver(self.settings, self.loop)


class FixedDnsMockAuthenticator(DnsMockAuthenticator):
    def _now_unix(self):
        return 2461449600
