from pathlib import Path

from em2.comms.auth import BaseAuthenticator

KEY_DIR = (Path(__file__).parent / 'keys').absolute()


class SimpleAuthenticator(BaseAuthenticator):
    def __init__(self, settings, loop):
        super().__init__(settings, loop)
        self._cache = {}
        self._key_file = KEY_DIR / 'public.pem'
        self.valid_signature_override = None

    async def _platform_key_exists(self, platform_key):
        exp = self._cache.get(platform_key, 1)
        return exp > self._now_unix()

    async def _get_public_key(self, platform):
        with self._key_file.open() as f:
            return f.read()

    async def _store_key(self, key, expiresat):
        self._cache[key] = expiresat

    def _check_domain_uses_platform(self, domain, platform_domain):
        pass

    def _valid_signature(self, signed_message, signature, public_key):
        if isinstance(self.valid_signature_override, bool):
            return self.valid_signature_override
        return super()._valid_signature(signed_message, signature, public_key)
