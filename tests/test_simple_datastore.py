import datetime

import hashlib
from em2.base import Conversations
from .py_datastore import SimpleDataStore


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


def test_conversation_extra_participant():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    write_access = conversations.participants.Permissions.WRITE
    conversations.participants.create(con_id, 'someone_different@example.com', write_access)
    assert len(con['participants']) == 2


def test_conversation_add_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
    msg1_id = list(con['messages'])[0]
    conversations.messages.create(con_id, 'text@example.com', 'I am find thanks.', msg1_id)
    assert len(con['messages']) == 2
    assert len(con['updates']) == 3
    last_update = con['updates'][-1]
    assert last_update['action'] == 'create'
    assert last_update['author'] == 'text@example.com'
    assert last_update['focus'] == 'messages'
    assert last_update['data'] == {}
    msg2_id = list(con['messages'])[1]
    assert last_update['focus_id'] == msg2_id


def test_conversation_edit_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
    msg1_id = list(con['messages'])[0]
    msg1 = con['messages'][msg1_id]
    assert msg1['body'] == 'hi, how are you?'
    conversations.messages.update(con_id, 'text@example.com', 'hi, how are you again?', msg1_id)
    assert msg1['body'] == 'hi, how are you again?'
    assert len(con['updates']) == 3
    last_update = con['updates'][-1]
    assert last_update['action'] == 'update'
    assert last_update['author'] == 'text@example.com'
    assert last_update['focus'] == 'messages'
    assert last_update['data'] == {'value': 'hi, how are you again?'}
    assert last_update['focus_id'] == msg1_id
