import pytest
from em2.base import perms, Action, Verbs, Components
from em2.exceptions import ComponentNotFound, VerbNotFound


async def test_correct_action(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    assert len(con['messages']) == 1
    a = Action('text@example.com', con_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='reply')
    assert len(con['messages']) == 2

    assert len(con['participants']) == 1
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert len(con['participants']) == 2

async def test_wrong_component(conversation):
    ds, ctrl, con_id = await conversation()
    con = ds.data[0]
    msg1_id = list(con['messages'])[0]
    a = Action('text@example.com', con_id, Verbs.ADD, 'foobar')
    with pytest.raises(ComponentNotFound):
        await ctrl.act(a, parent_id=msg1_id, body='reply')

async def test_non_existent_verb(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('text@example.com', con_id, 'foobar', Components.PARTICIPANTS)
    with pytest.raises(VerbNotFound) as excinfo:
        await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert 'foobar is not a valid verb' in str(excinfo)

async def test_wrong_verb(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('text@example.com', con_id, Verbs.LOCK, Components.PARTICIPANTS)
    with pytest.raises(VerbNotFound) as excinfo:
        await ctrl.act(a, email='someone_different@example.com', permissions=perms.WRITE)
    assert 'is not an available verb on' in str(excinfo)

async def test_wrong_args(conversation):
    ds, ctrl, con_id = await conversation()
    a = Action('text@example.com', con_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(TypeError) as excinfo:
        await ctrl.act(a, email='someone_different@example.com', foobar=True)
    assert 'add() got an unexpected keyword argument' in str(excinfo)
