from tests.conftest import python_dict  # NOQA


async def test_create(cli, url, foreign_server, get_conv):
    url_ = url('act', conv='key123', component='participant', verb='add', item='testing@local.com')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 204, await r.text()
    obj = await get_conv('key123')
    print(python_dict(obj))
    assert {
        'actions': None,
        'details': {
            'creator': 'test@already-authenticated.com',
            'key': 'key123',
            'published': True,
            'subject': 'Test Conversation',
            'ts': '2032-06-01T12:00:00.12345'
        },
        'messages': [
            {
                'active': True,
                'after': None,
                'body': 'this is the message',
                'key': 'msg-firstmessagekeyx',
                'relationship': None
            }
        ],
        'participants': [
            {
                'address': 'test@already-authenticated.com',
                'readall': False
            }
        ]
    } == obj


async def test_conv_no_address(cli, url):
    url_ = url('act', conv='123', component='participant', verb='add', item='')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 400, await r.text()
    assert 'participant address (item) missing' == await r.text()


async def test_conv_wrong_address(cli, url):
    url_ = url('act', conv='123', component='participant', verb='add', item='foo@bar.com')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 400, await r.text()
    assert 'participant "foo@bar.com" not linked to this platform' == await r.text()
