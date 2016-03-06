# TODO Could be replaced by basic user tests

import pytest

from em2.core import Controller, Action, Verbs
from em2.core.exceptions import UserNotFound
from tests.fixture_classes import SimpleDataStore, NullPropagator


async def test_basic_conversation():
    ds = SimpleDataStore(True)

    action = Action('sender@example.com', None, Verbs.ADD)
    await Controller(ds, NullPropagator()).act(action, subject='foo bar')
    print(ds)
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert con['subject'] == 'foo bar'


async def test_basic_conversation_dont_create_user():
    ds = SimpleDataStore(False)

    action = Action('sender@example.com', None, Verbs.ADD)
    with pytest.raises(UserNotFound):
        await Controller(ds, NullPropagator()).act(action, subject='foo bar')


async def test_basic_conversation_do_create_user():
    ds = SimpleDataStore(False)
    await ds.create_user(None, 'sender@example.com')

    action = Action('sender@example.com', None, Verbs.ADD)
    await Controller(ds, NullPropagator()).act(action, subject='foo bar')
    print(ds)
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert con['subject'] == 'foo bar'
