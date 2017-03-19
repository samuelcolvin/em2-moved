import datetime
import itertools
import json
from collections import OrderedDict
from copy import deepcopy

from em2.core import Components
from em2.ds.main import ConversationDataStore, DataStore, VoidContextManager
from em2.exceptions import ComponentNotFound, ConversationNotFound, EventNotFound
from tests.conftest import test_store


class UniversalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        try:
            return super().default(obj)
        except TypeError:
            return repr(obj)


class SimpleDataStore(DataStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_counter = itertools.count()
        self.data = test_store(self.settings.LOCAL_DOMAIN)
        self.user_counter = itertools.count()

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

    async def conversations_for_address(self, conn, address, limit=None, offset=None):
        results = []
        for cid, conv in self.data.items():
            p = next((p for p in conv['participants'].values() if p['address'] == address), None)
            if not p:
                continue
            cds = self.new_conv_ds(conv['conv_id'], conn)
            props = await cds.get_core_properties()
            props['conv_id'] = conv['conv_id']
            props['_id'] = cid
            results.append(props)
        results.sort(key=lambda c: (c['timestamp'], c['_id']), reverse=True)
        [r.pop('_id') for r in results]
        for r in results:
            yield r

    async def all_conversations(self):
        results = []
        for cid, conv in self.data.items():
            cds = self.new_conv_ds(conv['conv_id'], None)
            props = await cds.get_core_properties()
            props['conv_id'] = conv['conv_id']
            props['_id'] = cid
            results.append(props)
        results.sort(key=lambda c: (c['timestamp'], c['_id']), reverse=True)
        [r.pop('_id') for r in results]
        for r in results:
            yield r

    @property
    def conv_data_store(self):
        return SimpleConversationDataStore

    def conn_manager(self):
        return VoidContextManager()

    def get_conv(self, conv_id):
        for v in self.data.values():
            if v['conv_id'] == conv_id:
                return v
        raise ConversationNotFound('conversation {} not found'.format(conv_id))

    def __repr__(self):
        return json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder)


class SimpleConversationDataStore(ConversationDataStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conv_obj = None

    async def commit(self):
        pass

    @property
    def conv_obj(self):
        if self._conv_obj is None:
            self._conv_obj = self.ds.get_conv(self.conv)
        return self._conv_obj

    async def get_core_properties(self):
        return {k: self.conv_obj[k] for k in self._core_property_keys}

    async def save_event(self, action, **data):
        self.conv_obj['events'].append({
            'id': action.event_id,
            'actor': action.participant_id,
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
        for v in data.values():
            yield deepcopy(v)

    async def get_item_last_event(self, component, item_id):
        events = [e for e in self.conv_obj['events'] if e['component'] == component and e['item'] == item_id]
        if not events:
            raise EventNotFound('event for component {}:{} not found'.format(component, item_id))
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
