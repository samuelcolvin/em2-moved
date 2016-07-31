import aiodns

from arq import Actor


class RedisDNSMixin(Actor):
    _dft_value = b'1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._resolver = None

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self.loop)
        return self._resolver
