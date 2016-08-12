from arq.testing import RaiseWorker
from em2 import Settings
from em2.core import Action, Components, Controller, Verbs, perms
from em2.utils import now_unix_secs
from tests.fixture_classes import SimpleDataStore


async def test_authenticate(pusher):
    token = await pusher.authenticate('platform.remote.com')
    assert token.startswith('em2.local.com:2461536000:')
    async with pusher._redis_pool.get() as redis:
        v = await redis.get(b'ak:platform.remote.com')
        assert token == v.decode()
        ttl = await redis.ttl(b'ak:platform.remote.com')
        expiry = ttl + now_unix_secs()
        expected_expiry = 2461536000 - Settings().COMMS_PUSH_TOKEN_EARLY_EXPIRY
        assert abs(expiry - expected_expiry) < 10


async def test_get_node_local(pusher):
    r = await pusher.get_node('123', 'local.com')
    assert r == pusher.LOCAL


async def test_get_node_remote(pusher):
    r = await pusher.get_node('123', 'remote.com')
    assert r == 'em2.platform.remote.com'


async def test_publish_conv(pusher):
    ds = SimpleDataStore()
    ctrl = Controller(ds, pusher=pusher)
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar', body='great body')

    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    conv_id = await ctrl.act(a)  # conv id could have changed depending on milliseconds

    assert pusher.test_client.app['controller'].ds.data == {}
    worker = RaiseWorker(settings=pusher.settings, burst=True, loop=pusher.loop, existing_shadows=[pusher])
    await worker.run()
    data = pusher.test_client.app['controller'].ds.data
    assert len(data) == 1
    assert data[0]['conv_id'] == conv_id


async def test_publish_update_conv(pusher):
    ds = SimpleDataStore()
    ctrl = Controller(ds, pusher=pusher)
    conv_id = await ctrl.act(Action('sender@local.com', None, Verbs.ADD), subject='foo bar', body='great body')

    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@remote.com', permissions=perms.WRITE)
    conv_id = await ctrl.act(Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS))
    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.MESSAGES)

    assert pusher.test_client.app['controller'].ds.data == {}
    worker = RaiseWorker(settings=pusher.settings, burst=True, loop=pusher.loop, existing_shadows=[pusher])
    await worker.run(reuse=True)
    assert pusher.test_client.app['controller'].ds.data[0]['conv_id'] == conv_id

    # conversation is now published, add another message

    msg1_id = list(ctrl.ds.data[0]['messages'])[0]
    await ctrl.act(a, parent_id=msg1_id, body='this is another message')
    await worker.run()
