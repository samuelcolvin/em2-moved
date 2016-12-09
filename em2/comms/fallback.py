import logging
from em2 import Settings

logger = logging.getLogger('em2.fallback')


class FallbackHandler:
    def __init__(self, settings: Settings, *, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        super().__init__(**kwargs)

    async def ainit(self):
        pass

    async def push(self, action, data, participants):
        # TODO improve logging
        logger.info('%s to %s', action, participants)
