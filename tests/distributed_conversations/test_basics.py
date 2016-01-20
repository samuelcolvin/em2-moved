import datetime

import hashlib
from em2.base import Controller, Action, Verbs, Components, perms
from tests.fixture_classes import SimpleDataStore, NullPropagator
from .fixture_classes import SimplePropagator


async def test_create_basic_conversation():
    ds = SimpleDataStore()
    ctrl = Controller(ds, NullPropagator())
    await ctrl.conversations.create('sender@example.com', 'foo bar')
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    assert con['creator'] == 'sender@example.com'
    assert con['status'] == 'draft'
    assert con['subject'] == 'foo bar'
    assert isinstance(con['timestamp'], datetime.datetime)
    hash_data = bytes('sender@example.com_{}_foo bar'.format(con['timestamp'].isoformat()), 'utf8')
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert con['con_id'] == hash_result


async def test_create_conversation_add_external_participant():
    ds = SimpleDataStore()
    propagator = SimplePropagator()
    assert (propagator.all_platform_count, propagator.active_platform_count) == (0, 0)
    ctrl = Controller(ds, propagator, ref='ctrl1')
    remove_ctrl = Controller(SimpleDataStore(), NullPropagator(), ref='ctrl2')
    propagator.add_platform('@remote.com', remove_ctrl)
    assert (propagator.all_platform_count, propagator.active_platform_count) == (1, 0)
    con_id = await ctrl.conversations.create('sender@local.com', 'foo bar')
    assert len(ds.data[0]['participants']) == 1
    a = Action('sender@local.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    assert (propagator.all_platform_count, propagator.active_platform_count) == (1, 1)


async def test_publish_conversation():
    ds = SimpleDataStore()
    propagator = SimplePropagator()
    ctrl = Controller(ds, propagator, ref='ctrl1')
    other_ds = SimpleDataStore()
    remove_ctrl = Controller(other_ds, NullPropagator(), ref='ctrl2')
    propagator.add_platform('@remote.com', remove_ctrl)
    con_id = await ctrl.conversations.create('sender@local.com', 'the subject', 'the body')
    a = Action('sender@local.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    assert (propagator.all_platform_count, propagator.active_platform_count) == (1, 1)

    assert len(other_ds.data) == 0
    a = Action('sender@local.com', con_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert len(other_ds.data) == 1
    assert other_ds.data[0]['con_id'] == ds.data[0]['con_id']
    assert other_ds.data[0]['subject'] == 'the subject'
    assert len(other_ds.data[0]['messages']) == 1
    msg1 = list(other_ds.data[0]['messages'].values())[0]
    assert msg1['body'] == 'the body'
    assert other_ds.data[0]['timestamp'] == ds.data[0]['timestamp']
    assert len(other_ds.data[0]['participants']) == 2
    # TODO check email address and permissions
    print(ds.data[0]['messages'])
