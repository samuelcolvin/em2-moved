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

    def create_conversation(self, **kwargs):
        id = next(self.conversation_counter)
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            updates=[],
            **kwargs
        )
        return id

    def add_component(self, model, conversation, **kwargs):
        con_obj = self._get_con(conversation)
        if model not in con_obj:
            con_obj[model] = OrderedDict()
        if model == 'participants':
            id = next(con_obj['participant_counter'])
        else:
            id = kwargs['id']
        con_obj[model][id] = kwargs
        return id

    def edit_component(self, model, conversation, item_id, **kwargs):
        con_obj = self._get_con(conversation)
        items = con_obj.get(model)
        if items is None:
            raise ComponentNotFound('model "{}" not found on conversation {}'.format(model, conversation))
        item = items.get(item_id)
        if item is None:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, conversation))
        item.update(kwargs)

    def save_event(self, conversation, author, action, data, timestamp, focus_id, focus):
        con_obj = self._get_con(conversation)
        con_obj['updates'].append({
            'author': author,
            'action': action,
            'timestamp': timestamp,
            'focus_id': focus_id,
            'focus': focus,
            'data': data,
        })

    def _get_con(self, con_id):
        conversation = self.data.get(con_id)
        if conversation is None:
            raise ConversationNotFound('conversation {} not found in {} '
                                       'existing conversations'.format(con_id, len(self.data)))
        return conversation

    def get_message_count(self, con):
        con_obj = self._get_con(con)
        return len(con_obj.get('messages', {}))

    def check_message_exists(self, con, message_id):
        con_obj = self._get_con(con)
        msgs = con_obj.get('messages', {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return True

    def get_participant_id(self, con, participant_email):
        con_obj = self._get_con(con)
        prtis = con_obj.get('participants', {})
        for k, v in prtis.items():
            if v['email'] == participant_email:
                return k
        raise ComponentNotFound('participant {} not found in {}'.format(participant_email, prtis.keys()))

    @property
    def live_data(self):
        """
        Returns: non empty elements of self.data
        """
        return [v for v in self.data.values() if v]

    def print_pretty(self):
        print(json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder))
