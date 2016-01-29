import json
import datetime
from collections import OrderedDict

import itertools
from em2.core.common import Components
from em2.core.datastore import DataStore, ConversationDataStore
from em2.core.exceptions import ConversationNotFound, ComponentNotFound


class UniversalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        try:
            return super(UniversalEncoder, self).default(obj)
        except TypeError:
            return repr(obj)


class SimpleDataStore(DataStore):
    _conn_ctx = None

    def __init__(self):
        self.conversation_counter = itertools.count()
        self.data = {}
        super(SimpleDataStore, self).__init__()

    async def create_conversation(self, conn, **kwargs):
        id = next(self.conversation_counter)
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            events=[],
            locked=set(),
            expiration=None,
            **kwargs
        )
        return id

    @property
    def conv_data_store(self):
        return SimpleConversationDataStore

    def connection(self):
        # assert self._conn_ctx is None
        self._conn_ctx = VoidContextManager()
        return self._conn_ctx

    def reuse_connection(self):
        # assert self._conn_ctx is not None
        return self._conn_ctx

    def get_conv(self, conv_id):
        for v in self.data.values():
            if v['conv_id'] == conv_id:
                return v
        raise ConversationNotFound('conversation {} not found'.format(conv_id))

    def __repr__(self):
        return json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder)


class VoidContextManager:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class SimpleConversationDataStore(ConversationDataStore):
    def __init__(self, *args, **kwargs):
        super(SimpleConversationDataStore, self).__init__(*args, **kwargs)
        self._conv_obj = None

    @property
    def conv_obj(self):
        if self._conv_obj is None:
            self._conv_obj = self.ds.get_conv(self.conv)
        return self._conv_obj

    async def get_core_properties(self):
        return {k: self.conv_obj[k] for k in self._core_property_keys}

    async def save_event(self, event_id, action, data):
        self.conv_obj['events'].append({
            'id': event_id,
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': action.timestamp,
        })

    async def set_published_id(self, new_timestamp, new_id):
        self.conv_obj.update(
            draft_conv_id=self.conv_obj['conv_id'],
            conv_id=new_id,
            timestamp=new_timestamp,
        )
        self.conv = new_id

    # Status

    async def set_status(self, status):
        self.conv_obj['status'] = status

    # Ref

    async def set_ref(self, ref):
        self.conv_obj['ref'] = ref

    # Subject

    async def set_subject(self, subject):
        self.conv_obj['subject'] = subject

    # Component generic methods

    async def add_component(self, component, **kwargs):
        if component not in self.conv_obj:
            self.conv_obj[component] = OrderedDict()
        if component == Components.PARTICIPANTS:
            kwargs['id'] = next(self.conv_obj['participant_counter'])
        id = kwargs['id']
        self.conv_obj[component][id] = kwargs
        return id

    async def edit_component(self, component, item_id, **kwargs):
        item = self._get_conv_item(component, item_id)
        item.update(kwargs)

    async def delete_component(self, component, item_id):
        items = self._get_conv_items(component)
        try:
            del items[item_id]
        except KeyError:
            msg = '{} with id = {} not found on conversation {}'
            raise ComponentNotFound(msg.format(component, item_id, self.conv))

    async def lock_component(self, component, item_id):
        self._get_conv_item(component, item_id)
        self.conv_obj['locked'].add('{}:{}'.format(component, item_id))

    async def unlock_component(self, component, item_id):
        self.conv_obj['locked'].remove('{}:{}'.format(component, item_id))

    async def check_component_locked(self, component, item_id):
        items = self._get_conv_items(component)
        if item_id not in items:
            raise ComponentNotFound('message {} not found'.format(item_id))
        return '{}:{}'.format(component, item_id) in self.conv_obj['locked']

    async def get_all_component_items(self, component):
        data = self.conv_obj.get(component, {})
        return list(data.values())

    async def get_item_last_event(self, component, item_id):
        events = [e for e in self.conv_obj['events'] if e['component'] == component and e['item'] == item_id]
        print(events)
        if not events:
            return None, None
        event = events[-1]
        return event['id'], event['timestamp']

    # Messages

    async def get_message_meta(self, message_id):
        msgs = self.conv_obj.get(Components.MESSAGES, {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return {k: msg[k] for k in ('author', 'timestamp')}

    # Participants

    async def get_participant(self, participant_address):
        participants = self.conv_obj.get(Components.PARTICIPANTS, {})
        for v in participants.values():
            if v['address'] == participant_address:
                return v['id'], v['permissions']
        raise ComponentNotFound('participant {} not found'.format(participant_address))

    # internal methods

    def _get_conv_items(self, component):
        items = self.conv_obj.get(component)
        if items is None:
            raise ComponentNotFound('component "{}" not found on conversation {}'.format(component, self.conv))
        return items

    def _get_conv_item(self, component, item_id):
        items = self._get_conv_items(component)
        item = items.get(item_id)
        if item is None:
            msg = '{} with id = {} not found on conversation {}'
            raise ComponentNotFound(msg.format(component, item_id, self.conv))
        return item

    def __repr__(self):
        return self.__class__.__name__ + json.dumps(self.conv_obj, indent=2, sort_keys=True, cls=UniversalEncoder)
