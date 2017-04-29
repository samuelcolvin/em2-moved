from arq import BaseWorker
from em2 import setup_logging
from em2.comms import RedisDNSAuthenticator
from em2.comms.web.push import WebDNSPusher

from em2.settings import Settings


class Worker(BaseWorker):
    """
    arq worker used to execute jobs
    """
    shadows = [WebDNSPusher, RedisDNSAuthenticator]

    def __init__(self, **kwargs):
        self.settings = kwargs.pop('settings', None) or Settings()
        setup_logging(self.settings)
        kwargs['redis_settings'] = self.settings.redis
        super().__init__(**kwargs)

    async def shadow_kwargs(self):
        return dict(
            redis_settings=self.redis_settings,
            settings=self.settings,
            is_shadow=True,
            loop=self.loop,
            existing_pool=await self.get_redis_pool(),
        )
