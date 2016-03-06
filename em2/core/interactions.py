import logging

from .enums import Enum
from .components import Components, hash_id

logger = logging.getLogger('em2')


class Verbs(Enum):
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'
    UNLOCK = 'unlock'
    # is there anywhere we need this apart from actually publishing conversations?
    # seems ugly to have a verb for one use
    PUBLISH = 'publish'


class _Interaction:
    repr_attrs = []
    cds = conn = actor_id = actor_addr = None

    async def set_participant(self):
        self.actor_id, self.perm = await self.cds.get_participant(self.actor_addr)

    @property
    def known_conversation(self):
        raise NotImplementedError

    @property
    def is_remote(self):
        raise NotImplementedError

    def __repr__(self):
        return '<Action({})>'.format(', '.join('{}={}'.format(a, getattr(self, a)) for a in self.repr_attrs))


class Action(_Interaction):
    """
    Define something someone does.
    """
    repr_attrs = ['actor_addr', 'actor_id', 'perm', 'conv', 'verb', 'component', 'item', 'timestamp',
                  'event_id', 'parent_event_id']

    def __init__(self, actor, conversation, verb, component=Components.CONVERSATIONS,
                 item=None, timestamp=None, event_id=None, parent_event_id=None):
        self.perm = None
        self.actor_addr = actor
        self.conv = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.event_id = event_id
        self.parent_event_id = parent_event_id

    @property
    def is_remote(self):
        return self.event_id is not None

    @property
    def known_conversation(self):
        return not (self.component == Components.CONVERSATIONS and self.verb == Verbs.ADD)

    def calc_event_id(self):
        return hash_id(self.timestamp, self.actor_addr, self.conv, self.verb, self.component, self.item)


class RVerbs(Enum):
    GET = 'get'
    LIST = 'list'
    SEARCH = 'search'


class Retrieval(_Interaction):
    """
    Define a request from someone to get data.
    """
    repr_attrs = ['actor_addr', 'actor_id', 'conv', 'verb', 'component', 'is_remote']

    def __init__(self, user, conversation=None, verb=RVerbs.GET, component=Components.CONVERSATIONS, is_remote=False):
        self.actor_addr = user
        self.conv = conversation
        self.verb = verb
        self.component = component
        self._is_remote = is_remote

    @property
    def is_remote(self):
        return self._is_remote

    @property
    def known_conversation(self):
        return not (self.component == Components.CONVERSATIONS and self.verb in {RVerbs.LIST, RVerbs.SEARCH})
