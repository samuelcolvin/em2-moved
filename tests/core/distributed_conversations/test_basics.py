import datetime
import hashlib
from copy import deepcopy

from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from tests.fixture_classes import SimpleDataStore, SimplePusher

async def test_create_basic_conversation(controller):
    action = Action('sender@example.com', None, Verbs.ADD)
    await controller.act(action, subject='foo bar')
    ds = controller.ds
    assert len(ds.data) == 1
    conv = ds.data[0]
    assert len(conv['participants']) == 1
    assert len(conv['events']) == 0
    assert conv['creator'] == 'sender@example.com'
    assert conv['status'] == 'draft'
    assert conv['subject'] == 'foo bar'
    assert isinstance(conv['timestamp'], datetime.datetime)
    hash_data = bytes('sender@example.com_{}_foo bar'.format(conv['timestamp'].isoformat()), 'utf8')
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert conv['conv_id'] == hash_result


async def test_create_conversation_add_external_participant():
    ds = SimpleDataStore()
    pusher = SimplePusher(Settings(LOCAL_DOMAIN='local.com'))
    assert len(pusher.remotes) == 0
    ctrl = Controller(ds, pusher, ref='ctrl1')
    remote_ctrl = Controller(SimpleDataStore(), ref='ctrl2')
    pusher.network.add_node('remote.com', remote_ctrl)
    assert len(pusher.remotes) == 0

    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar')
    assert len(ds.data[0]['participants']) == 1
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert len(ds.data[0]['participants']) == 2
    assert len(pusher.remotes) == 1


async def test_publish_conversation():
    ds = SimpleDataStore()
    pusher = SimplePusher(Settings(LOCAL_DOMAIN='local.com'))
    ctrl = Controller(ds, pusher, ref='ctrl1')
    other_ds = SimpleDataStore()
    remote_ctrl = Controller(other_ds, ref='ctrl2')
    pusher.network.add_node('remote.com', remote_ctrl)
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='the subject', body='the body')
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
    new_conv_id = await ctrl1.act(a)
    assert len(ctrl2.ds.data) == 1

    assert new_conv_id != conv_id
    assert new_conv_id == ctrl1.ds.data[0]['conv_id']

    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']
