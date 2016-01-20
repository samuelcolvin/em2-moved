from em2.base import Action, Verbs, Components


async def test_publish_conversation2(two_controllers):
    ctrl1, ctrl2, con_id = await two_controllers()

    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 0)
    a = Action('user@ctrl1.com', con_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl1.act(a)
    assert (len(ctrl1.ds.data), len(ctrl2.ds.data)) == (1, 1)

    con_id = ctrl1.ds.data[0]['con_id']
    msg1_id = list(ctrl2.ds.data[0]['messages'])[0]
    a = Action('user@ctrl2.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl2.act(a, parent_id=msg1_id, body='this is a reply')

    assert ctrl1.ds.data[0]['participants'] == ctrl2.ds.data[0]['participants']
    assert ctrl1.ds.data[0]['messages'] == ctrl2.ds.data[0]['messages']
