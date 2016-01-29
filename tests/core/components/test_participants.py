from collections import OrderedDict
import pytest
from em2.core.base import perms, Action, Verbs, Components
from em2.core.exceptions import InsufficientPermissions


async def test_extra_participant(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert len(con['events']) == 0
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert con['participants'] == OrderedDict([
        (0, {'address': 'test@example.com', 'id': 0, 'permissions': 'full'}),
        (1, {'address': 'someone_different@example.com', 'id': 1, 'permissions': 'write'}),
    ])
    assert len(con['events']) == 1


async def test_add_participant_readonly(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='readonly@example.com', permissions=perms.READ)
    assert len(ds.data[0]['participants']) == 2
    a = Action('readonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, address='readonly2@example.com', permissions=perms.READ)
    assert 'FULL or WRITE permission are required to add participants' in str(excinfo)


async def test_add_participant_write_create_write(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly2@example.com', permissions=perms.WRITE)


async def test_add_participant_write_create_full(conversation):
    ds, ctrl, con_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    a = Action('writeonly@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, address='full_perms@example.com', permissions=perms.FULL)
    assert 'FULL permission are required to add participants with FULL permissions' in str(excinfo)
