import hashlib
from em2.base import Action, Verbs, Components


async def test_create_conversation_with_message(conversation):
    ds, ctrl, con_id = await conversation()
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


async def test_conversation_add_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='I am find thanks.')
    assert len(con['messages']) == 2
    assert len(con['updates']) == 1

    assert con['updates'][0]['verb'] == 'add'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {}

    msg2_id = list(con['messages'])[1]
    assert con['updates'][0]['component_id'] == msg2_id


async def test_conversation_edit_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    msg1 = con['messages'][msg1_id]
    assert msg1['body'] == 'hi, how are you?'
    assert msg1['author'] == 0
    a = Action('text@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id)
    await ctrl.act(a, body='hi, how are you again?')
    assert msg1['body'] == 'hi, how are you again?'
    assert msg1['author'] == 0
    assert len(con['updates']) == 1
    assert con['updates'][0]['verb'] == 'edit'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {'value': 'hi, how are you again?'}
    assert con['updates'][0]['component_id'] == msg1_id


async def test_conversation_delete_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.DELETE, Components.MESSAGES, item=msg1_id)
    await ctrl.act(a)
    assert len(con['messages']) == 0
    assert len(con['updates']) == 1
    assert con['updates'][0]['verb'] == 'delete'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {}
    assert con['updates'][0]['component_id'] == msg1_id


async def test_conversation_lock_unlock_message(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    assert len(con['messages']) == 1
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.LOCK, Components.MESSAGES, item=msg1_id)
    await ctrl.act(a)
    assert len(con['locked']) == 1
    locked_v = list(con['locked'])[0]
    assert locked_v == 'messages:{}'.format(msg1_id)

    a = Action('text@example.com', con_id, Verbs.UNLOCK, Components.MESSAGES, item=msg1_id)
    await ctrl.act(a)
    assert len(con['locked']) == 0
