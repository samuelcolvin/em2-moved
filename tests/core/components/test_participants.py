from collections import OrderedDict

import pytest

from em2.core import Components, perms, Action, Verbs
from em2.exceptions import InsufficientPermissions


async def test_extra_participant(conversation):
    ds, ctrl, conv_id = await conversation()
    assert len(ds.data) == 1
    conv = ds.data[0]
    assert len(conv['participants']) == 1
    assert len(conv['events']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert conv['participants'] == OrderedDict([
        (0, {'address': 'test@example.com', 'id': 0, 'permissions': 'full'}),
        (1, {'address': 'someone_different@example.com', 'id': 1, 'permissions': 'write'}),
    ])
    assert len(conv['events']) == 2


async def test_add_participant_readonly(conversation):
    ds, ctrl, conv_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='readonly@example.com', permissions=perms.READ)
    assert len(ds.data[0]['participants']) == 2
    a = Action('readonly@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, address='readonly2@example.com', permissions=perms.READ)
    assert 'FULL or WRITE permission are required to add participants' in str(excinfo)


async def test_add_participant_write_create_write(conversation):
    ds, ctrl, conv_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    a = Action('writeonly@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly2@example.com', permissions=perms.WRITE)


async def test_add_participant_write_create_full(conversation):
    ds, ctrl, conv_id = await conversation()
    assert len(ds.data[0]['participants']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='writeonly@example.com', permissions=perms.WRITE)
    assert len(ds.data[0]['participants']) == 2
    a = Action('writeonly@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(InsufficientPermissions) as excinfo:
        await ctrl.act(a, address='full_perms@example.com', permissions=perms.FULL)
    assert 'FULL permission are required to add participants with FULL permissions' in str(excinfo)
