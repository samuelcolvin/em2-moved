from asyncio import Future
from aiohttp import ClientOSError
from em2.comms.http.push import HttpDNSPusher


def future_result(loop, result):
    r = Future(loop=loop)
    r.set_result(result)
    return r


async def test_get_nodes_not_existing(pusher):
    await pusher.get_nodes('foo@nomx.com')
    await pusher.get_nodes('foo@nomx.com')
    async with await pusher.get_redis_conn() as redis:
        node = await redis.get(b'dn:nomx.com')
        assert node == b'F'


async def test_save_nodes_existing(pusher):
    async with await pusher.get_redis_conn() as redis:
        await redis.set(b'dn:nomx.com', b'somethingelse.com')
    await pusher.get_nodes('foo@nomx.com')
    async with await pusher.get_redis_conn() as redis:
        node = await redis.get(b'dn:nomx.com')
        assert node == b'somethingelse.com'


async def test_no_mx(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    mock_mx_query.return_value = future_result(loop, [])
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_authenticate.called is False


async def test_mx_em2(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    mock_mx_query.return_value = future_result(loop, [(0, 'em2.example.com')])
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')
    mock_authenticate.return_value = future_result(loop, 'the_key')

    v = await pusher.get_node('example.com')
    assert v == 'em2.example.com'

    mock_mx_query.assert_called_with('example.com')
    mock_authenticate.assert_called_with('em2.example.com')


async def test_mx_not_em2(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    mock_mx_query.return_value = future_result(loop, [(0, 'notem2.example.com')])

    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')
    mock_authenticate.return_value = future_result(loop, 'the_key')

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_authenticate.called is False


async def test_client_os_error(pusher, loop, mocker):
    mock_mx_query = mocker.patch('em2.comms.http.push.HttpDNSPusher.mx_query')
    mock_mx_query.return_value = future_result(loop, [(0, 'em2.example.com')])
    mock_post = mocker.patch('em2.comms.http.push.aiohttp.ClientSession.post')
    mock_post.side_effect = ClientOSError('foobar')

    v = await pusher.get_node('example.com')
    assert v == HttpDNSPusher.FALLBACK

    mock_mx_query.assert_called_with('example.com')
    assert mock_post.call_args[0] == ('https://em2.example.com/authenticate',)


async def test_dns_error(pusher, mocker):
    mock_authenticate = mocker.patch('em2.comms.http.push.HttpDNSPusher.authenticate')

    v = await pusher.get_node('error.com')
    assert v == HttpDNSPusher.FALLBACK

    assert mock_authenticate.called is False
