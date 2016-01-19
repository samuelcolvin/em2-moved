import logging
import json
import datetime
from collections import OrderedDict

import itertools
from em2.base import logger, Components
from em2.send import BasePropagator
from em2.data_store import DataStore, ConversationDataStore
from em2.exceptions import ConversationNotFound, ComponentNotFound

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(message)s'))
logger.addHandler(handler)
# logger.setLevel(logging.DEBUG)


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
    def __init__(self):
        self.conversation_counter = itertools.count()
        self.data = {}
        super(SimpleDataStore, self).__init__()

    async def create_conversation(self, **kwargs):
        id = str(next(self.conversation_counter))
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            updates=[],
            locked=set(),
            **kwargs
        )
        return id

    @property
    def con_data_store(self):
        return ConversationSimpleDataStore

    def get_con(self, con_id):
        for v in self.data.values():
            if v['con_id'] == con_id:
                return v
        raise ConversationNotFound('conversation {} not found'.format(con_id))

    def __repr__(self):
        return json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder)


class ConversationSimpleDataStore(ConversationDataStore):
    def __init__(self, *args, **kwargs):
        super(ConversationSimpleDataStore, self).__init__(*args, **kwargs)
        self.con_obj = self.ds.get_con(self.con)

    async def save_event(self, action, data, timestamp):
        self.con_obj['updates'].append({
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': timestamp,
        })

    async def set_published_id(self, new_timestamp, new_id):
        self.con_obj['draft_con_id'] = self.con_obj['con_id']
        self.con_obj['con_id'] = new_id
        self.con_obj['timestamp'] = new_timestamp

    async def set_status(self, status):
        self.con_obj['status'] = status

    async def get_status(self):
        return self.con_obj['status']

    async def add_component(self, model, **kwargs):
        if model not in self.con_obj:
            self.con_obj[model] = OrderedDict()
        if model == 'participants':
            kwargs['id'] = next(self.con_obj['participant_counter'])
        id = kwargs['id']
        self.con_obj[model][id] = kwargs
        return id

    async def edit_component(self, model, item_id, **kwargs):
        item = self._get_con_item(model, item_id)
        item.update(kwargs)

    async def delete_component(self, model, item_id):
        items = self._get_con_items(model)
        try:
            del items[item_id]
        except KeyError:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, self.con))

    async def lock_component(self, model, item_id):
        self._get_con_item(model, item_id)
        self.con_obj['locked'].add('{}:{}'.format(model, item_id))

    async def unlock_component(self, model, item_id):
        self.con_obj['locked'].remove('{}:{}'.format(model, item_id))

    async def get_message_locked(self, model, item_id):
        return '{}:{}'.format(model, item_id) in self.con_obj['locked']

    async def get_message_count(self):
        return len(self.con_obj.get('messages', {}))

    async def get_first_message(self):
        messages = self.con_obj[Components.MESSAGES]
        return list(messages.values())[0]

    async def get_subject(self):
        return self.con_obj['subject']

    async def set_subject(self, subject):
        self.con_obj['subject'] = subject

    async def get_participant_count(self):
        return len(self.con_obj.get(Components.PARTICIPANTS, {}))

    async def get_message_author(self, message_id):
        msgs = self.con_obj.get(Components.MESSAGES, {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return msg['author']

    async def get_participant(self, participant_address):
        prtis = self.con_obj.get(Components.PARTICIPANTS, {})
        for v in prtis.values():
            if v['email'] == participant_address:
                return v['id'], v['permissions']
        raise ComponentNotFound('participant {} not found in {}'.format(participant_address, prtis.keys()))

    def _get_con_items(self, model):
        items = self.con_obj.get(model)
        if items is None:
            raise ComponentNotFound('model "{}" not found on conversation {}'.format(model, self.con))
        return items

    def _get_con_item(self, model, item_id):
        items = self._get_con_items(model)
        item = items.get(item_id)
        if item is None:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, self.con))
        return item

    def __repr__(self):
        return json.dumps(self.con_obj, indent=2, sort_keys=True, cls=UniversalEncoder)


class NullPropagator(BasePropagator):
    async def add_participant(self, action, participant_addr):
        pass

    async def remove_participant(self, action, participant_addr):
        pass

    async def propagate(self, action, data, timestamp):
        pass
