from asyncio import Future

import aiohttp
from arq.testing import RaiseWorker

from em2 import Settings
from em2.comms.http.push import HttpDNSPusher
from em2.core import Action, Components, Verbs, perms
from em2.utils import now_unix_secs


async def test_push_no_mx(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    r = Future(loop=loop)
    r.set_result([])
    mock_mx_query.return_value = r
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_authenticate.called is False
    await pusher.close()


async def test_push_mx_em2(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    r = Future(loop=loop)
    r.set_result([(0, 'em2.example.com')])
    mock_mx_query.return_value = r
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')
    r = Future(loop=loop)
    r.set_result('the_key')
    mock_authenticate.return_value = r

    v = await pusher.get_node('example.com')
    assert v == 'em2.example.com'

    mock_mx_query.assert_called_with('example.com')
    mock_authenticate.assert_called_with('em2.example.com')
    await pusher.close()


async def test_push_mx_not_em2(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    r = Future(loop=loop)
    r.set_result([(0, 'notem2.example.com')])
    mock_mx_query.return_value = r

    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')
    r = Future(loop=loop)
    r.set_result('the_key')
    mock_authenticate.return_value = r

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_authenticate.called is False
    await pusher.close()


async def test_push_client_os_error(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    r = Future(loop=loop)
    r.set_result([(0, 'em2.example.com')])
    mock_mx_query.return_value = r
    mock_post = mocker.patch('em2.comms.http.push.aiohttp.ClientSession.post')
    mock_post.side_effect = aiohttp.ClientOSError('foobar')

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_post.call_args[0] == ('https://em2.example.com/authenticate',)
    await pusher.close()


async def test_authenticate(ctrl_pusher):
    ctrl, pusher = await ctrl_pusher()
    token = await pusher.authenticate('em2.platform.remote.com')
    assert token.startswith('em2.local.com:2461536000:')
    async with pusher._redis_pool.get() as redis:
        v = await redis.get(b'ak:em2.platform.remote.com')
        assert token == v.decode()
        ttl = await redis.ttl(b'ak:em2.platform.remote.com')
        expiry = ttl + now_unix_secs()
        expected_expiry = 2461536000 - Settings().COMMS_PUSH_TOKEN_EARLY_EXPIRY
        assert abs(expiry - expected_expiry) < 10


async def test_get_node_local(ctrl_pusher):
    ctrl, pusher = await ctrl_pusher()
    r = await pusher.get_node('local.com')
    assert r == pusher.LOCAL


async def test_get_node_remote(ctrl_pusher):
    ctrl, pusher = await ctrl_pusher()
    r = await pusher.get_node('remote.com')
    assert r == 'em2.platform.remote.com'


async def test_publish_conv(ctrl_pusher):
    ctrl, pusher = await ctrl_pusher()
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


async def test_publish_update_conv(ctrl_pusher):
    ctrl, pusher = await ctrl_pusher()
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
