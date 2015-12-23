import logging
import json
import datetime
from collections import OrderedDict

import itertools
from em2.base import logger
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
        try:
            return super(UniversalEncoder, self).default(obj)
        except TypeError:
            return repr(obj)


class SimpleDataStore(DataStore):
    def __init__(self, *args, **kwargs):
        self.conversation_counter = itertools.count()
        self.data = {}
        super(SimpleDataStore, self).__init__(*args, **kwargs)

    async def save_event(self, action, component_id, data, timestamp):
        con_obj = self._get_con(action.con)
        con_obj['updates'].append({
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'component_id': component_id,
            'data': data,
            'timestamp': timestamp,
        })

    async def create_conversation(self, **kwargs):
        id = next(self.conversation_counter)
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            updates=[],
            **kwargs
        )
        return id

    async def add_component(self, model, conversation, **kwargs):
        con_obj = self._get_con(conversation)
        if model not in con_obj:
            con_obj[model] = OrderedDict()
        if model == 'participants':
            kwargs['id'] = next(con_obj['participant_counter'])
        id = kwargs['id']
        con_obj[model][id] = kwargs
        return id

    async def edit_component(self, model, conversation, item_id, **kwargs):
        con_obj = self._get_con(conversation)
        items = con_obj.get(model)
        if items is None:
            raise ComponentNotFound('model "{}" not found on conversation {}'.format(model, conversation))
        item = items.get(item_id)
        if item is None:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, conversation))
        item.update(kwargs)

    def _get_con(self, con_id):
        conversation = self.data.get(con_id)
        if conversation is None:
            raise ConversationNotFound('conversation {} not found in {} '
                                       'existing conversations'.format(con_id, len(self.data)))
        return conversation

    async def get_message_count(self, con):
        con_obj = self._get_con(con)
        return len(con_obj.get('messages', {}))

    async def get_participant_count(self, con):
        con_obj = self._get_con(con)
        return len(con_obj.get('participants', {}))

    async def get_message_author(self, con, message_id):
        con_obj = self._get_con(con)
        msgs = con_obj.get('messages', {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return msg['author']

    async def get_participant(self, con, participant_address):
        con_obj = self._get_con(con)
        prtis = con_obj.get('participants', {})
        for v in prtis.values():
            if v['email'] == participant_address:
                return v['id'], v['permissions']
        raise ComponentNotFound('participant {} not found in {}'.format(participant_address, prtis.keys()))

    def print_pretty(self):
        print(json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder))
