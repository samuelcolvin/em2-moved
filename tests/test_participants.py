from em2.base import perms, Action, Verbs, Components


async def test_conversation_extra_participant(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert len(con['participants']) == 2
    assert len(con['updates']) == 1
