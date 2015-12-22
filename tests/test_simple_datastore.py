import logging
import json
import datetime

import hashlib
import itertools
from em2.base import Conversations, logger
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

    def create_component(self, model, **kwargs):
        con_id = kwargs['conversation']
        if model not in self.data[con_id]:
            self.data[con_id][model] = {}
        if model == 'participants':
            id = next(self.data[con_id]['participant_counter'])
        else:
            id = kwargs['id']
        self.data[con_id][model][id] = kwargs
        return id

    def record_change(self, conversation, author, action, focus_id, focus):
        con_obj = self._get_con(conversation)
        con_obj['updates'].append({
            'author': author,
            'action': action,
            'focus_id': focus_id,
            'focus': focus,
        })
        return super(SimpleDataStore, self).record_change(conversation, author, action, focus_id, focus)

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


def test_create_basic_conversation():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    conversations.create('text@example.com', 'foo bar')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['updates']) == 1
    assert con['creator'] == 'text@example.com'
    assert con['status'] == 'draft'
    assert con['subject'] == 'foo bar'
    assert isinstance(con['timestamp'], datetime.datetime)
    hash_data = bytes('{}_{}_{}'.format(con['creator'], con['timestamp'].isoformat(), con['subject']), 'utf8')
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert con['global_id'] == hash_result


def test_create_conversation_with_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
