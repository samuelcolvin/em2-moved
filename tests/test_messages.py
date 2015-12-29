import hashlib
import pytest
from em2.base import perms, Action, Verbs, Components
from em2.exceptions import InsufficientPermissions


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


async def test_add_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['updates']) == 0
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='I am fine thanks.')
    assert len(con['messages']) == 2
    assert len(con['updates']) == 1

    assert con['updates'][0]['verb'] == 'add'
    assert con['updates'][0]['actor'] == 0
    assert con['updates'][0]['component'] == 'messages'
    assert con['updates'][0]['data'] == {}

    msg2_id = list(con['messages'])[1]
    assert con['updates'][0]['component_id'] == msg2_id


async def test_edit_message(conversation):
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


async def test_delete_message(conversation):
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


async def test_lock_unlock_message(conversation):
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


async def test_add_message_missing_perms(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='readonly@example.com', permissions=perms.READ)

    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('readonly@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, parent_id=msg1_id, body='reply')
    assert 'FULL or WRITE access required to add messages' in str(excinfo)


async def test_edit_message_right_person(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='writeonly@example.com', permissions=perms.WRITE)

    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='reply')

    msg2_id = None
    for msg2_id, info in con['messages'].items():
        if info['parent'] == msg1_id:
            break
    assert con['messages'][msg2_id]['body'] == 'reply'

    a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg2_id)
    await ctrl.act(a, body='changed message')
    assert con['messages'][msg2_id]['body'] == 'changed message'


async def test_edit_message_wrong_person(conversation):
    ds, ctrl, con_id = await conversation()
    msg1_id = list(ds.data[0]['messages'])[0]

    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='writeonly@example.com', permissions=perms.WRITE)

    a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, body='changed message')
    assert 'To edit a message authored by another participant FULL permissions are requires' in str(excinfo)
