import datetime
import hashlib
import time
from copy import deepcopy

from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from em2.utils import to_unix_ms


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
    hash_data = 'sender@example.com_{}_foo bar'.format(to_unix_ms(conv['timestamp'])).encode()
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert conv['conv_id'] == hash_result


async def test_create_conversation_add_external_participant(reset_store, loop):
    s_local = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='local.com',
    )
    ctrl = Controller(s_local, loop=loop)
    await ctrl.pusher.init_ds()
    s_remote = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='remote.com'
    )
    remote_ctrl = Controller(s_remote, loop=loop)
    await remote_ctrl.pusher.init_ds()
    ctrl.pusher.network.add_node('remote.com', remote_ctrl)

    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar')
    assert len(ctrl.ds.data[0]['participants']) == 1
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert len(ctrl.ds.data[0]['participants']) == 2


async def test_publish_conversation(reset_store, loop):
    local_settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='local.com',
    )
    ctrl = Controller(local_settings, loop=loop)

    remote_settings = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='remote.com',
    )
    remote_ctrl = Controller(remote_settings, loop=loop)

    await ctrl.pusher.init_ds()

    ctrl.pusher.network.add_node('remote.com', remote_ctrl)
    remote_ctrl.pusher.network.add_node('local.com', ctrl)
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='the subject', body='the body')
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)

    messages_before = deepcopy(ctrl.ds.data[0]['messages'])
    assert len(remote_ctrl.ds.data) == 0
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert ctrl.ds.data[0]['messages'] == messages_before
    assert len(remote_ctrl.ds.data) == 1
    assert remote_ctrl.ds.data[0]['conv_id'] == ctrl.ds.data[0]['conv_id']
    assert remote_ctrl.ds.data[0]['subject'] == 'the subject'
    assert len(remote_ctrl.ds.data[0]['messages']) == 1
    msg1 = list(remote_ctrl.ds.data[0]['messages'].values())[0]
    assert msg1['body'] == 'the body'
    assert remote_ctrl.ds.data[0]['timestamp'] == ctrl.ds.data[0]['timestamp']

    assert ctrl.ds.data[0]['participants'] == remote_ctrl.ds.data[0]['participants']
    assert ctrl.ds.data[0]['messages'] == remote_ctrl.ds.data[0]['messages']


async def test_publish_conversation2(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert len(ctrl2.ds.data) == 0
    time.sleep(0.001)  # to make sure the conv_id changes as time ms have change
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    new_conv_id = await ctrl1.act(a)
    assert len(ctrl2.ds.data) == 1

    assert new_conv_id != conv_id
    assert new_conv_id == ctrl1.ds.data[0]['conv_id']

    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']
