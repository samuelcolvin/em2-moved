import pytest

from em2.core import Action, Verbs, Components, perms
from em2.exceptions import BadDataException
from tests.conftest import datetime_tz


async def test_publish_reply(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)

    conv_id = ctrl1.ds.data[0]['conv_id']  # conv published, get new id
    msg1_id = list(ctrl2.ds.data[0]['messages'])[0]
    a = Action('user@ctrl2.com', conv_id, Verbs.ADD, Components.MESSAGES)
    await ctrl2.act(a, parent_id=msg1_id, body='this is a reply')

    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']


async def test_publish_reply_bad_ts(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)

    conv_id = ctrl1.ds.data[0]['conv_id']
    msg1_id = list(ctrl2.ds.data[0]['messages'])[0]
    a = Action('user@ctrl2.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=datetime_tz(year=2000))
    a.event_id = a.calc_event_id()
    with pytest.raises(BadDataException) as excinfo:
        await ctrl1.act(a, parent_id=msg1_id, body='this is a reply')
    assert excinfo.value.args[0] == 'timestamp not after parent timestamp: 2000-01-01 00:00:00+00:00'


async def test_draft_add_remove_recipient(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert len(ctrl1.ds.data[0]['participants']) == 2
    assert len(ctrl2.ds.data) == 0
    assert len(ctrl1.pusher.remotes) == 0

    conv_id = ctrl1.ds.data[0]['conv_id']
    a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl1.act(a, address='someone_else@ctrl1.com', permissions=perms.READ)

    assert len(ctrl1.ds.data[0]['participants']) == 3
    assert len(ctrl2.ds.data) == 0
    assert len(ctrl1.pusher.remotes) == 0

    a = Action('user@ctrl1.com', conv_id, Verbs.DELETE, Components.PARTICIPANTS)
    await ctrl1.act(a, address='someone_else@ctrl1.com')
    assert len(ctrl1.ds.data[0]['participants']) == 2
    assert len(ctrl2.ds.data) == 0
    assert len(ctrl1.pusher.remotes) == 0


async def test_publish_add_remove_recipient(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()
    assert len(ctrl1.pusher.remotes) == 0

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)
    assert len(ctrl1.ds.data[0]['participants']) == 2

    conv_id = ctrl1.ds.data[0]['conv_id']
    assert len(ctrl1.pusher.remotes[conv_id]) == 2
    a = Action('user@ctrl1.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl1.act(a, address='someone_else@ctrl1.com', permissions=perms.READ)

    assert len(ctrl1.ds.data[0]['participants']) == 3
    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']

    a = Action('user@ctrl1.com', conv_id, Verbs.DELETE, Components.PARTICIPANTS)
    await ctrl1.act(a, address='someone_else@ctrl1.com')
    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert len(ctrl1.ds.data[0]['participants']) == 2
    assert len(ctrl1.pusher.remotes[conv_id]) == 2


async def test_publish_remove_domain(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()
    assert len(ctrl1.pusher.remotes) == 0

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)
    assert len(ctrl1.ds.data[0]['participants']) == 2

    conv_id = ctrl1.ds.data[0]['conv_id']
    assert len(ctrl1.pusher.remotes[conv_id]) == 2

    a = Action('user@ctrl1.com', conv_id, Verbs.DELETE, Components.PARTICIPANTS)
    await ctrl1.act(a, address='user@ctrl2.com')
    assert len(ctrl1.ds.data[0]['participants']) == 1
    assert len(ctrl1.pusher.remotes[conv_id]) == 1
