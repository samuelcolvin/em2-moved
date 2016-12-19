import hashlib
import time
from copy import deepcopy
from datetime import datetime, timedelta

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
    assert isinstance(conv['timestamp'], datetime)
    hash_data = 'sender@example.com_{}_foo bar'.format(to_unix_ms(conv['timestamp'])).encode()
    hash_result = hashlib.sha256(hash_data).hexdigest()
    assert conv['conv_id'] == hash_result


async def test_create_conversation_add_external_participant(get_redis_pool, reset_store, loop):
    s_local = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='local.com',
    )
    ctrl = Controller(s_local, loop=loop)
    await ctrl.pusher.ainit()
    s_remote = Settings(
        DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
        PUSHER_CLS='tests.fixture_classes.SimplePusher',
        LOCAL_DOMAIN='remote.com'
    )
    remote_ctrl = Controller(s_remote, loop=loop)
    await remote_ctrl.pusher.ainit()
    ctrl.pusher.network.add_node('remote.com', remote_ctrl)

    pool = await get_redis_pool()
    ctrl.pusher._redis_pool = pool
    remote_ctrl.pusher._redis_pool = pool

    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar')
    assert len(ctrl.ds.data[0]['participants']) == 1
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)
    assert len(ctrl.ds.data[0]['participants']) == 2


def compare_messages(ctrl1, ctrl2):
    m1 = ctrl1.ds.data[0]['messages']
    m2 = ctrl2.ds.data[0]['messages']
    assert m1.keys() == m2.keys()
    v1 = list(m1.values())
    v2 = list(m2.values())
    for i in range(len(m1.keys())):
        vv1 = v1[i]
        ts1 = vv1.pop('timestamp')
        vv2 = v2[i]
        ts2 = vv2.pop('timestamp')
        assert vv1 == vv2
        assert abs(ts1 - ts2) < timedelta(milliseconds=1)


async def test_publish_conversation(get_redis_pool, reset_store, loop):
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

    await ctrl.pusher.ainit()
    pool = await get_redis_pool()
    ctrl.pusher._redis_pool = pool
    remote_ctrl.pusher._redis_pool = pool

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
    assert abs(ctrl.ds.data[0]['timestamp'] - remote_ctrl.ds.data[0]['timestamp']) < timedelta(milliseconds=1)

    assert ctrl.ds.data[0]['participants'] == remote_ctrl.ds.data[0]['participants']
    compare_messages(ctrl, remote_ctrl)


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
    compare_messages(ctrl1, ctrl2)
