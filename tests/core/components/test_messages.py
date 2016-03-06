import hashlib
import datetime

import pytest

from em2.core import Components, perms, Action, Verbs
from em2.core.exceptions import InsufficientPermissions, ComponentLocked, ComponentNotLocked


async def test_create_conversation_with_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['messages']) == 1
    assert len(con['events']) == 1

    assert con['events'][0]['verb'] == 'add'
    assert con['events'][0]['actor'] == 0
    assert con['events'][0]['component'] == 'messages'
    assert con['events'][0]['data'] == {}

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
    assert len(con['events']) == 1
    msg1_id = list(con['messages'])[0]
    a = Action('test@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='I am fine thanks.')
    assert len(con['messages']) == 2
    assert len(con['events']) == 2

    assert con['events'][1]['verb'] == 'add'
    assert con['events'][1]['actor'] == 0
    assert con['events'][1]['component'] == 'messages'
    assert con['events'][1]['data'] == {}

    msg2_id = list(con['messages'])[1]
    assert con['events'][1]['item'] == msg2_id
    msg2 = con['messages'][msg2_id]
    # can't easily get the timestamp value in a sensible way
    timestamp = msg2.pop('timestamp')
    assert isinstance(timestamp, datetime.datetime)
    msg2_expected = {
        'author': 0,
        'id': msg2_id,
        'body': 'I am fine thanks.',
        'parent': msg1_id,
    }
    assert msg2 == msg2_expected


async def test_edit_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['events']) == 1
    msg1_id = list(con['messages'])[0]
    msg1 = con['messages'][msg1_id]
    assert msg1['body'] == 'hi, how are you?'
    assert msg1['author'] == 0
    peid = ds.data[0]['events'][0]['id']
    a = Action('test@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    await ctrl.act(a, body='hi, how are you again?')
    assert msg1['body'] == 'hi, how are you again?'
    assert msg1['author'] == 0
    assert len(con['events']) == 2
    assert con['events'][1]['verb'] == 'edit'
    assert con['events'][1]['actor'] == 0
    assert con['events'][1]['component'] == 'messages'
    assert con['events'][1]['data'] == {'value': 'hi, how are you again?'}
    assert con['events'][1]['item'] == msg1_id


async def test_delete_message(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['messages']) == 1
    assert len(con['events']) == 1
    msg1_id = list(con['messages'])[0]
    peid = ds.data[0]['events'][0]['id']
    a = Action('test@example.com', con_id, Verbs.DELETE, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    await ctrl.act(a)
    assert len(con['messages']) == 0
    assert len(con['events']) == 2
    assert con['events'][1]['verb'] == 'delete'
    assert con['events'][1]['actor'] == 0
    assert con['events'][1]['component'] == 'messages'
    assert con['events'][1]['data'] == {}
    assert con['events'][1]['item'] == msg1_id


async def test_lock_unlock_message(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    assert len(con['messages']) == 1
    msg1_id = list(con['messages'])[0]
    peid = ds.data[0]['events'][0]['id']
    a = Action('test@example.com', con_id, Verbs.LOCK, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    await ctrl.act(a)
    peid = a.calc_event_id()
    assert len(con['locked']) == 1
    locked_v = list(con['locked'])[0]
    assert locked_v == 'messages:{}'.format(msg1_id)

    a = Action('test@example.com', con_id, Verbs.UNLOCK, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    await ctrl.act(a)
    assert len(con['locked']) == 0


async def test_lock_edit(conversation):
    ds, ctrl, con_id = await conversation()
    msg1_id = list(ds.data[0]['messages'])[0]
    assert len(ds.data[0]['events']) == 1
    peid = ds.data[0]['events'][0]['id']
    a = Action('test@example.com', con_id, Verbs.LOCK, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    await ctrl.act(a)
    peid = a.calc_event_id()
    a = Action('test@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id, parent_event_id=peid)
    with pytest.raises(ComponentLocked) as excinfo:
        await ctrl.act(a, body='hi, how are you again?')
    assert 'ComponentLocked: messages with id = {} locked'.format(msg1_id) in str(excinfo)


async def test_wrong_unlock(conversation):
    ds, ctrl, con_id = await conversation()
    msg1_id = list(ds.data[0]['messages'])[0]
    a = Action('test@example.com', con_id, Verbs.UNLOCK, Components.MESSAGES, item=msg1_id)
    with pytest.raises(ComponentNotLocked) as excinfo:
        await ctrl.act(a)
    assert 'ComponentNotLocked: messages with id = {} not locked'.format(msg1_id) in str(excinfo)

async def test_add_message_missing_perms(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='readonly@example.com', permissions=perms.READ)

    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('readonly@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, parent_id=msg1_id, body='reply')
    assert 'FULL or WRITE access required to add messages' in str(excinfo)


async def test_edit_message_missing_perms(conversation):
    ds, ctrl, con_id = await conversation()
    msg1_id = list(ds.data[0]['messages'])[0]

    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='readonly@example.com', permissions=perms.READ)

    a = Action('readonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, body='changed message')
    assert 'To edit a message requires FULL or WRITE permissions' in str(excinfo)


async def test_edit_message_successful(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)

    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='reply')
    # have to do after act so timestamp is set
    parent_event_id = a.calc_event_id()

    msg2_id = None
    for msg2_id, info in con['messages'].items():
        if info['parent'] == msg1_id:
            break
    assert con['messages'][msg2_id]['body'] == 'reply'

    a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg2_id,
               parent_event_id=parent_event_id)
    await ctrl.act(a, body='changed message')
    assert con['messages'][msg2_id]['body'] == 'changed message'


async def test_edit_first_message(conversation):
    ds, ctrl, con_id = await conversation()

    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    assert con['messages'][msg1_id]['body'] == 'hi, how are you?'

    print(con['events'])
    # parent_event_id = con['events']
    #
    # a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id,
    #            parent_event_id=parent_event_id)
    # await ctrl.act(a, body='changed message')


async def test_edit_message_wrong_person(conversation):
    ds, ctrl, con_id = await conversation()
    msg1_id = list(ds.data[0]['messages'])[0]

    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)

    a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg1_id)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, body='changed message')
    assert 'To edit a message authored by another participant FULL permissions are requires' in str(excinfo)


# async def test_edit_message_no_parent_eid(conversation):
#     ds, ctrl, con_id = await conversation()
#     a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
#     await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)
#
#     con = ds.data[0]
#     msg1_id = list(con['messages'])[0]
#     a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.MESSAGES)
#     await ctrl.act(a, parent_id=msg1_id, body='reply')
#
#     a = Action('writeonly@example.com', con_id, Verbs.EDIT, Components.MESSAGES, item=msg2_id,
#                parent_event_id=parent_event_id)
#     await ctrl.act(a, body='changed message')
#     assert con['messages'][msg2_id]['body'] == 'changed message'
