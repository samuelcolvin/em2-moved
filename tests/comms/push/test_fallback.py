import pytest

from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from tests.fixture_classes.authenicator import get_private_key


@pytest.yield_fixture
def ctrl_pusher(loop, reset_store):
    _ctrl = None, None

    async def _create():
        nonlocal _ctrl
        settings = Settings(
            LOCAL_DOMAIN='em2.local.com',
            PRIVATE_DOMAIN_KEY=get_private_key(),
            DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
            PUSHER_CLS='tests.fixture_classes.push.HttpMockedDNSPusher',
        )
        _ctrl = Controller(settings, loop=loop)
        _ctrl.pusher._concurrency_enabled = False
        await _ctrl.pusher.ainit()
        async with await _ctrl.pusher.get_redis_conn() as redis:
            await redis.flushall()
        return _ctrl

    yield _create

    async def close():
        await _ctrl.pusher.close()

    loop.run_until_complete(close())


async def test_no_mx(ctrl_pusher, mocker, caplog):
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')

    ctrl = await ctrl_pusher()
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar', body='great body')

    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@fallback.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)  # conv id could have changed depending on milliseconds
    assert mock_authenticate.called is False
    assert 'Components.CONVERSATIONS . Verbs.ADD, from: sender@local.com, to: (1) receiver@fallback.com' in caplog
