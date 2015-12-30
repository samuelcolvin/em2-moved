import pytest
from em2.base import perms, Action, Verbs, Components
from em2.exceptions import InsufficientPermissions


async def test_extra_participant(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data['0']
    assert len(con['participants']) == 1
    assert len(con['updates']) == 0
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert len(con['participants']) == 2
    assert len(con['updates']) == 1


async def test_add_participant_readonly(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data['0']['participants']) == 1
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='readonly@example.com', permissions=perms.READ)
    assert len(ds.data['0']['participants']) == 2
    a = Action('readonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, email='readonly2@example.com', permissions=perms.READ)
    assert 'FULL or WRITE permission are required to add participants' in str(excinfo)


async def test_add_participant_write_create_write(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data['0']['participants']) == 1
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data['0']['participants']) == 2
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='writeonly2@example.com', permissions=perms.WRITE)


async def test_add_participant_write_create_full(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data['0']['participants']) == 1
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data['0']['participants']) == 2
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, email='full_perms@example.com', permissions=perms.FULL)
    assert 'FULL permission are required to add participants with FULL permissions' in str(excinfo)
