import pytest

from em2.core import Action, Components, Verbs, perms
from em2.exceptions import BadDataException, ComponentNotFound, VerbNotFound

async def test_correct_action(conversation):
    ds, ctrl, conv_id = await conversation()
    conv = ds.data[0]
    msg1_id = list(conv['messages'])[0]
    assert len(conv['messages']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.MESSAGES)
    await ctrl.act(a, parent_id=msg1_id, body='reply')
    assert len(conv['messages']) == 2

    assert len(conv['participants']) == 1
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert len(conv['participants']) == 2


async def test_wrong_component(conversation):
    ds, ctrl, conv_id = await conversation()
    conv = ds.data[0]
    with pytest.raises(ComponentNotFound):
        Action('test@example.com', conv_id, Verbs.ADD, 'foobar')


async def test_non_existent_verb(conversation):
    ds, ctrl, conv_id = await conversation()
    with pytest.raises(VerbNotFound) as excinfo:
        Action('test@example.com', conv_id, 'foobar', Components.PARTICIPANTS)
    assert 'foobar is not a valid verb' in str(excinfo)


async def test_wrong_verb(conversation):
    ds, ctrl, conv_id = await conversation()
    a = Action('test@example.com', conv_id, Verbs.LOCK, Components.PARTICIPANTS)
    with pytest.raises(VerbNotFound) as excinfo:
        await ctrl.act(a, address='someone_different@example.com', permissions=perms.WRITE)
    assert 'is not an available verb on' in str(excinfo)


async def test_wrong_args(conversation):
    ds, ctrl, conv_id = await conversation()
    a = Action('test@example.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    with pytest.raises(BadDataException) as excinfo:
        await ctrl.act(a, address='someone_different@example.com', foobar=True)
    assert excinfo.value.args[0] == "Participants.add: missing a required argument: 'permissions'"
