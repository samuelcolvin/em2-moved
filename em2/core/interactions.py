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


class Action:
    """
    Define something someone does.
    """
    def __init__(self, actor, conversation, verb, component=Components.CONVERSATIONS,
                 item=None, timestamp=None, event_id=None, parent_event_id=None):
        self.cds = None
        self.actor_id = None
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

    async def prepare(self):
        self.actor_id, self.perm = await self.cds.get_participant(self.actor_addr)

    def calc_event_id(self):
        return hash_id(self.timestamp, self.actor_addr, self.conv, self.verb, self.component, self.item)

    def __repr__(self):
        attrs = ['actor_addr', 'actor_id', 'perm', 'conv', 'verb', 'component', 'item', 'timestamp',
                 'event_id', 'parent_event_id']
        return '<Action({})>'.format(', '.join('{}={}'.format(a, getattr(self, a)) for a in attrs))
