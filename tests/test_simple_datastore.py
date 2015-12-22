import datetime
import pytest

import hashlib
from em2.base import Conversations, perms
from .py_datastore import SimpleDataStore


@pytest.mark.asyncio
async def test_create_basic_conversation():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    await conversations.create('text@example.com', 'foo bar')
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


async def test_create_conversation_with_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    await conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
    msg = list(con['messages'].values())[0]
    assert msg['parent'] is None
    assert msg['author'] == 0
    assert msg['body'] == 'hi, how are you?'


async def test_conversation_extra_participant():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = await conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    write_access = perms.WRITE
    await conversations.participants.add(con_id, 'someone_different@example.com', write_access, 'text@example.com')
    assert len(con['participants']) == 2


async def test_conversation_add_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = await conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
    msg1_id = list(con['messages'])[0]
    await conversations.messages.add(con_id, 'text@example.com', 'I am find thanks.', msg1_id)
    assert len(con['messages']) == 2
    assert len(con['updates']) == 3
    last_update = con['updates'][-1]
    assert last_update['action'] == 'add'
    assert last_update['author'] == 0
    assert last_update['focus'] == 'messages'
    assert last_update['data'] == {}
    msg2_id = list(con['messages'])[1]
    assert last_update['focus_id'] == msg2_id


async def test_conversation_edit_message():
    ds = SimpleDataStore()
    conversations = Conversations(ds)
    con_id = await conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 2
    msg1_id = list(con['messages'])[0]
    msg1 = con['messages'][msg1_id]
    assert msg1['body'] == 'hi, how are you?'
    assert msg1['author'] == 0
    await conversations.messages.edit(con_id, 'text@example.com', 'hi, how are you again?', msg1_id)
    assert msg1['body'] == 'hi, how are you again?'
    assert msg1['author'] == 0
    assert len(con['updates']) == 3
    last_update = con['updates'][-1]
    assert last_update['action'] == 'edit'
    assert last_update['author'] == 0
    assert last_update['focus'] == 'messages'
    assert last_update['data'] == {'value': 'hi, how are you again?'}
    assert last_update['focus_id'] == msg1_id
