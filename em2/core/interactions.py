import logging

from em2.utils import Enum, to_unix_timestamp

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
    _attr_names = []
    cds = conn = participant_id = address = None

    async def set_participant(self):
        self.participant_id, self.perm = await self.cds.get_participant(self.address)

    @property
    def known_conversation(self):
        raise NotImplementedError

    @property
    def is_remote(self):
        raise NotImplementedError

    @property
    def attrs(self):
        return {a: getattr(self, a) for a in self._attr_names}

    def __repr__(self):
        cls_name = self.__class__.__name__
        return '<{}({})>'.format(cls_name, ', '.join('{}={}'.format(a, getattr(self, a)) for a in self._attr_names))


class Action(_Interaction):
    """
    Define something someone does.
    """
    _attr_names = ['address', 'participant_id', 'perm', 'conv', 'verb', 'component', 'item', 'timestamp',
                   'event_id', 'parent_event_id']

    def __init__(self, address, conversation, verb, component=Components.CONVERSATIONS,
                 *, item=None, timestamp=None, event_id=None, parent_event_id=None):
        """
        :param address: address of person performing action
        :param conversation: id of the conversation being acted upon
        :param verb: what is being done, see Verb
        :param component: what it's being done to, see Components
        :param item: id of the item being acted upon
        :param timestamp: remote only, datetime action originally occurred
        :param event_id: remote only, hash of event
        :param parent_event_id: id of the event which this action follows
        """
        self.perm = None
        self.address = address
        self.conv = conversation
        self.verb = verb
        self.component = component
        self.item = item
        self.timestamp = timestamp
        self.event_id = event_id
        self.parent_event_id = parent_event_id
        self._status = None

    @property
    def is_remote(self):
        return self.event_id is not None

    @property
    def known_conversation(self):
        return not (self.component == Components.CONVERSATIONS and self.verb == Verbs.ADD)

    def calc_event_id(self):
        ts = self.timestamp and to_unix_timestamp(self.timestamp)
        return hash_id(ts, self.address, self.conv, self.verb, self.component, self.item)

    async def get_conv_status(self):
        if self._status is None:
            self._status = await self.cds.get_status()
        return self._status


class RVerbs(Enum):
    GET = 'get'
    LIST = 'list'
    SEARCH = 'search'


class Retrieval(_Interaction):
    """
    Define a request from someone to get data.
    """
    _attr_names = ['address', 'participant_id', 'conv', 'verb', 'component', 'is_remote']

    def __init__(self, address, conversation=None, verb=RVerbs.GET, component=Components.CONVERSATIONS,
                 is_remote=False):
        self.address = address
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
