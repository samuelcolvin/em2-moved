import datetime

import hashlib
from em2.base import Controller, perms, Action, Verbs, Components
from .py_datastore import SimpleDataStore


async def test_create_basic_conversation():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    await ctrl.conversations.create('text@example.com', 'foo bar')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    assert con['creator'] == 'text@example.com'
    assert con['status'] == 'draft'
    assert con['subject'] == 'foo bar'
    assert isinstance(con['timestamp'], datetime.datetime)
    hash_data = bytes('{}_{}_{}'.format(con['creator'], con['timestamp'].isoformat(), con['subject']), 'utf8')
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert con['global_id'] == hash_result


async def test_create_conversation_with_message():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg = list(con['messages'].values())[0]
    assert msg['parent'] is None
    assert msg['author'] == 0
    assert msg['body'] == 'hi, how are you?'
    hash_data = bytes('{}_{}_{}_None'.format(con['creator'], msg['timestamp'].isoformat(), msg['body']), 'utf8')
    msg_id = hashlib.sha1(hash_data).hexdigest()
    assert msg['id'] == msg_id


async def test_conversation_extra_participant():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    con_id = await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANT)
    await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert len(con['participants']) == 2
    assert len(con['updates']) == 1


async def test_conversation_add_message():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    con_id = await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.ADD, Components.MESSAGE)
    await ctrl.act(a, body='I am find thanks.', parent=msg1_id)
    assert len(con['messages']) == 2
    assert len(con['updates']) == 1

    assert con['updates'][0]['verb'] == 'add'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {}

    msg2_id = list(con['messages'])[1]
    assert con['updates'][0]['component_id'] == msg2_id


async def test_conversation_edit_message():
    ds = SimpleDataStore()
    ctrl = Controller(ds)
    con_id = await ctrl.conversations.create('text@example.com', 'foo bar', 'hi, how are you?')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    msg1 = con['messages'][msg1_id]
    assert msg1['body'] == 'hi, how are you?'
    assert msg1['author'] == 0
    a = Action('text@example.com', con_id, Verbs.EDIT, Components.MESSAGE)
    await ctrl.act(a, id=msg1_id, body='hi, how are you again?')
    assert msg1['body'] == 'hi, how are you again?'
    assert msg1['author'] == 0
    assert len(con['updates']) == 1
    assert con['updates'][0]['verb'] == 'edit'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {'value': 'hi, how are you again?'}
    assert con['updates'][0]['component_id'] == msg1_id
