import pytest
from em2.core.base import Action, Verbs, Components
from em2.core.exceptions import BadDataException


async def test_publish_reply(two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)

    conv_id = ctrl1.ds.data[0]['conv_id']
    msg1_id = list(ctrl2.ds.data[0]['messages'])[0]
    a = Action('user@ctrl2.com', conv_id, Verbs.ADD, Components.MESSAGES)
    await ctrl2.act(a, parent_id=msg1_id, body='this is a reply')

    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']


async def test_publish_reply_bad_ts(timestamp, two_controllers):
    ctrl1, ctrl2, conv_id = await two_controllers()

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)

    conv_id = ctrl1.ds.data[0]['conv_id']
    msg1_id = list(ctrl2.ds.data[0]['messages'])[0]
    a = Action('user@ctrl2.com', conv_id, Verbs.ADD, Components.MESSAGES, timestamp=timestamp, remote=True)
    with pytest.raises(BadDataException):
        await ctrl1.act(a, parent_id=msg1_id, body='this is a reply')
