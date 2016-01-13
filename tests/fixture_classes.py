import logging
import json
import datetime
from collections import OrderedDict

import itertools
from em2.base import logger, Components
from em2.send import BasePropagator
from em2.data_store import DataStore
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
    def __init__(self, *args, **kwargs):
        self.conversation_counter = itertools.count()
        self.data = {}
        super(SimpleDataStore, self).__init__(*args, **kwargs)

    async def save_event(self, action, data, timestamp):
        con_obj = self._get_con(action.con)
        con_obj['updates'].append({
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': timestamp,
        })

    async def create_conversation(self, **kwargs):
        id = str(next(self.conversation_counter))
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            updates=[],
            locked=set(),
            **kwargs
        )
        return id

    async def set_status(self, con, status):
        con_obj = self._get_con(con)
        con_obj['status'] = status

    async def get_status(self, con):
        con_obj = self._get_con(con)
        return con_obj['status']

    async def add_component(self, model, conversation, **kwargs):
        con_obj = self._get_con(conversation)
        if model not in con_obj:
            con_obj[model] = OrderedDict()
        if model == 'participants':
            kwargs['id'] = next(con_obj['participant_counter'])
        id = kwargs['id']
        con_obj[model][id] = kwargs
        return id

    async def edit_component(self, model, con, item_id, **kwargs):
        item = self._get_con_item(model, con, item_id)
        item.update(kwargs)

    async def delete_component(self, model, con, item_id):
        items = self._get_con_items(model, con)
        try:
            del items[item_id]
        except KeyError:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, con))

    async def lock_component(self, model, con, item_id):
        self._get_con_item(model, con, item_id)
        con_obj = self._get_con(con)
        con_obj['locked'].add('{}:{}'.format(model, item_id))

    async def unlock_component(self, model, con, item_id):
        con_obj = self._get_con(con)
        con_obj['locked'].remove('{}:{}'.format(model, item_id))

    async def get_message_locked(self, model, con, item_id):
        con_obj = self._get_con(con)
        return '{}:{}'.format(model, item_id) in con_obj['locked']

    async def get_message_count(self, con):
        con_obj = self._get_con(con)
        return len(con_obj.get('messages', {}))

    async def get_first_message(self, con):
        con_obj = self._get_con(con)
        messages = con_obj[Components.MESSAGES]
        return list(messages.values())[0]

    async def get_subject(self, con):
        con_obj = self._get_con(con)
        return con_obj['subject']

    async def set_subject(self, con, subject):
        con_obj = self._get_con(con)
        con_obj['subject'] = subject

    async def get_participant_count(self, con):
        con_obj = self._get_con(con)
        return len(con_obj.get(Components.PARTICIPANTS, {}))

    async def get_message_author(self, con, message_id):
        con_obj = self._get_con(con)
        msgs = con_obj.get(Components.MESSAGES, {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return msg['author']

    async def get_participant(self, con, participant_address):
        con_obj = self._get_con(con)
        prtis = con_obj.get(Components.PARTICIPANTS, {})
        for v in prtis.values():
            if v['email'] == participant_address:
                return v['id'], v['permissions']
        raise ComponentNotFound('participant {} not found in {}'.format(participant_address, prtis.keys()))

    def _get_con(self, con_id):
        conversation = self.data.get(con_id)
        if conversation is None:
            raise ConversationNotFound('conversation {} not found'.format(con_id))
        return conversation

    def _get_con_items(self, model, con_id):
        con_obj = self._get_con(con_id)
        items = con_obj.get(model)
        if items is None:
            raise ComponentNotFound('model "{}" not found on conversation {}'.format(model, con_id))
        return items

    def _get_con_item(self, model, con_id, item_id):
        items = self._get_con_items(model, con_id)
        item = items.get(item_id)
        if item is None:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, con_id))

        return item

    def __repr__(self):
        return json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder)


class NullPropagator(BasePropagator):
    async def add_participant(self, action, participant_addr):
        pass

    async def remove_participant(self, action, participant_addr):
        pass

    async def propagate(self, action, data, timestamp):
        pass
