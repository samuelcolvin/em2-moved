from em2.core import Controller, Action, Verbs
from tests.fixture_classes import SimpleDataStore, NullPropagator


async def test_basic_conversation():
    ds = SimpleDataStore()

    action = Action('sender@example.com', None, Verbs.ADD)
    await Controller(ds, NullPropagator()).act(action, subject='foo bar')
    print(ds)
    assert len(ds.data) == 1
    con = ds.data[0]
    assert len(con['participants']) == 1
    assert con['subject'] == 'foo bar'
