from pathlib import Path

from em2.comms.auth import BaseAuthenticator

KEY_DIR = (Path(__file__).parent / 'keys').absolute()


class SimpleAuthenticator(BaseAuthenticator):
    def __init__(self, settings=None):
        super().__init__(settings)
        self._cache = {}
        with (KEY_DIR / 'public.pem').open() as f:
            self.public_key_value = f.read()
        self.valid_signature_override = None

    async def _platform_key_exists(self, platform_key):
        exp = self._cache.get(platform_key, 1)
        return exp > self._now_unix()

    async def _get_public_key(self, platform):
        return self.public_key_value

    async def _store_key(self, key, expiresat):
        self._cache[key] = expiresat

    async def _check_domain_uses_platform(self, domain, platform_domain):
        return platform_domain.endswith(domain)

    def _valid_signature(self, signed_message, signature, public_key):
        if isinstance(self.valid_signature_override, bool):
            return self.valid_signature_override
        return super()._valid_signature(signed_message, signature, public_key)
