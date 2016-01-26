import datetime
import hashlib
from copy import deepcopy

from em2.core.base import Controller, Action, Verbs, Components, perms
from tests.tools.fixture_classes import SimpleDataStore, NullPropagator, SimplePropagator


async def test_create_basic_conversation(controller):
    await controller.conversations.create('sender@example.com', 'foo bar')
    ds = controller.ds
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
    assert con['conv_id'] == hash_result


async def test_create_conversation_add_external_participant():
    ds = SimpleDataStore()
    propagator = SimplePropagator()
    assert (propagator.all_platform_count, propagator.active_platform_count) == (0, 0)
    ctrl = Controller(ds, propagator, ref='ctrl1')
    remote_ctrl = Controller(SimpleDataStore(), NullPropagator(), ref='ctrl2')
    propagator.add_platform('@remote.com', remote_ctrl)
    assert (propagator.all_platform_count, propagator.active_platform_count) == (1, 0)
    conv_id = await ctrl.conversations.create('sender@local.com', 'foo bar')
    assert len(ds.data[0]['participants']) == 1
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    assert (propagator.all_platform_count, propagator.active_platform_count) == (1, 1)


async def test_publish_conversation():
    ds = SimpleDataStore()
    propagator = SimplePropagator()
    ctrl = Controller(ds, propagator, ref='ctrl1')
    other_ds = SimpleDataStore()
    remote_ctrl = Controller(other_ds, NullPropagator(), ref='ctrl2')
    propagator.add_platform('@remote.com', remote_ctrl)
    conv_id = await ctrl.conversations.create('sender@local.com', 'the subject', 'the body')
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)

    messages_before = deepcopy(ds.data[0]['messages'])
    assert len(other_ds.data) == 0
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert ds.data[0]['messages'] == messages_before
    assert len(other_ds.data) == 1
    assert other_ds.data[0]['conv_id'] == ds.data[0]['conv_id']
    assert other_ds.data[0]['subject'] == 'the subject'
    assert len(other_ds.data[0]['messages']) == 1
    msg1 = list(other_ds.data[0]['messages'].values())[0]
    assert msg1['body'] == 'the body'
    assert other_ds.data[0]['timestamp'] == ds.data[0]['timestamp']
    assert ds.data[0]['participants'] == other_ds.data[0]['participants']
    assert ds.data[0]['messages'] == other_ds.data[0]['messages']


async def test_publish_conversation2(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert len(ctrl2.ds.data) == 0
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert len(ctrl2.ds.data) == 1

    new_conv_id = ctrl1.ds.data[0]['conv_id']
    assert new_conv_id != conv_id
    assert new_conv_id == ctrl2.ds.data[0]['conv_id']
    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']
