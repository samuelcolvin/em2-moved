

async def test_publish(cli, url, foreign_server, get_conv, debug):
    assert foreign_server.app['request_log'] == []
    url_ = url('create', conv='key12345678')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': 'yyyyyyyyyyyyyyyyyyyy',
        'em2-participant': 'testing@local.com',
    })
    assert r.status == 204, await r.text()
    obj = await get_conv('key12345678')
    assert obj['details']['subject'] == 'Test Conversation'
    assert foreign_server.app['request_log'] == [
        'POST /auth/ > 201',
        'GET /get/key12345678/ > 200',
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
    ]


async def test_add_participant(cli, url, foreign_server, get_conv, db_conn):
    assert foreign_server.app['request_log'] == []
    url_ = url('act', conv='key12345678', component='participant', verb='add', item='testing@local.com')
    r = await cli.post(url_, headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': 'yyyyyyyyyyyyyyyyyyyy',
        'em2-participant': 'testing@local.com',
    })
    assert r.status == 204, await r.text()
    obj = await get_conv('key12345678')
    assert {
        'actions': [
            {
                'actor': 'test@already-authenticated.com',
                'body': None,
                'component': 'participant',
                'key': 'yyyyyyyyyyyyyyyyyyyy',
                'message': None,
                'parent': None,
                'participant': 'testing@local.com',
                'timestamp': '2032-06-01T13:00:00.12345',
                'verb': 'add'
            }
        ],
        'details': {
            'creator': 'test@already-authenticated.com',
            'key': 'key12345678',
            'published': True,
            'subject': 'Test Conversation',
            'created_ts': '2032-06-01T12:00:00.12345',
        },
        'messages': [
            {
                'deleted': False,
                'after': None,
                'body': 'this is the message',
                'format': 'markdown',
                'key': 'msg-firstmessagekeyx',
                'relationship': None
            }
        ],
        'participants': [
            {'address': 'test@already-authenticated.com'},
            {'address': 'testing@local.com'},
        ]
    } == obj
    assert foreign_server.app['request_log'] == [
        'POST /auth/ > 201',
        'GET /get/key12345678/ > 200',
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
    ]
    updated_ts = await db_conn.fetchval('SELECT to_json(updated_ts) FROM conversations')
    assert updated_ts == '"2032-06-01T13:00:00.12345"'


async def test_conv_missing(cli, url, foreign_server):
    url_ = url('act', conv='123', component='message', verb='modify', item='')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 404, await r.text()
    assert 'conversation not found' == await r.text()
    assert foreign_server.app['request_log'] == []


async def test_no_address(cli, url, foreign_server):
    url_ = url('act', conv='123', component='participant', verb='add', item='')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
    })
    assert r.status == 400, await r.text()
    assert 'header "em2-participant" missing' == await r.text()
    assert foreign_server.app['request_log'] == []


async def test_conv_wrong_address(cli, url, foreign_server):
    url_ = url('act', conv='123', component='participant', verb='add', item='foo@bar.com')
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
        'em2-participant': 'foo@bar.com',
    })
    assert r.status == 400, await r.text()
    assert 'participant "foo@bar.com" not linked to this platform' == await r.text()
    assert foreign_server.app['request_log'] == []


async def test_publish_conv_exists(cli, url, foreign_server, get_conv, debug):
    assert foreign_server.app['request_log'] == []
    url_ = url('create', conv='key12345678')
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': 'yyyyyyyyyyyyyyyyyyyy',
        'em2-participant': 'testing@local.com',
    }
    r = await cli.post(url_, data='foobar', headers=headers)
    assert r.status == 204, await r.text()
    obj = await get_conv('key12345678')
    assert obj['details']['subject'] == 'Test Conversation'
    r = await cli.post(url_, data='foobar', headers=headers)
    assert r.status == 409, await r.text()
    assert foreign_server.app['request_log'] == [
        'POST /auth/ > 201',
        'GET /get/key12345678/ > 200',
        'GET /check-user-node/ > 200',
        'GET /check-user-node/ > 200',
    ]


async def test_publish_wrong_address(cli, url, foreign_server):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@already-authenticated.com',
        'em2-timestamp': '1',
        'em2-action-key': '123',
        'em2-participant': 'foo@bar.com',
    }
    r = await cli.post(url('create', conv='key12345678'), data='foobar', headers=headers)
    assert r.status == 400, await r.text()
    assert 'participant "foo@bar.com" not linked to this platform' == await r.text()
    assert foreign_server.app['request_log'] == []
