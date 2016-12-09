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

    def get_from_to(self, action, participants):
        _from = None
        _to = []
        for p in participants:
            if p['address'] == action.address:
                _from = p
            else:
                _to.append(p)
        return _from, _to

    async def push(self, action, data, participants):
        # TODO we're going to always need the subject
        _from, _to = self.get_from_to(action, participants)
        logger.info('%.6s %s . %s, from: %s, to: (%d) %s', action.conv, action.component, action.verb, _from['address'],
                    len(_to), ', '.join(p['address'] for p in _to))
