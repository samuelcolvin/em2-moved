import pytest

from em2.core.controller import Action, Verbs, Components
from em2.core.components import perms
from em2.core.exceptions import ComponentNotFound, VerbNotFound, BadDataException


async def test_correct_action(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    assert len(con['messages']) == 1
    a = Action('test@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='reply')
    assert len(con['messages']) == 2

    assert len(con['participants']) == 1
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert len(con['participants']) == 2

async def test_wrong_component(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('test@example.com', con_id, Verbs.ADD, 'foobar')
    with pytest.raises(ComponentNotFound):
        await ctrl.act(a, parent_id=msg1_id, body='reply')

async def test_non_existent_verb(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('test@example.com', con_id, 'foobar', Components.PARTICIPANTS)
    with pytest.raises(VerbNotFound) as excinfo:
        await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert 'foobar is not a valid verb' in str(excinfo)

async def test_wrong_verb(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('test@example.com', con_id, Verbs.LOCK, Components.PARTICIPANTS)
    with pytest.raises(VerbNotFound) as excinfo:
        await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert 'is not an available verb on' in str(excinfo)

async def test_wrong_args(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('test@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(BadDataException) as excinfo:
        await ctrl.act(a, address='someone_different@example.com', foobar=True)
    assert 'Wrong kwargs for add, got:' in str(excinfo)
