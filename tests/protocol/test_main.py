from datetime import datetime

from arq.utils import to_unix_ms

from em2 import Settings
from em2.core import Relationships
from em2.utils.network import check_server

from ..conftest import CloseToNow
from ..fixture_classes import PLATFORM, TIMESTAMP, VALID_SIGNATURE


async def test_get_conv(cli, conv, url):
    url_ = url('get', conv=conv.key)
    r = await cli.get(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-participant': conv.creator_address,
    })
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert {
        'actions': None,
        'details': {
            'creator': 'test@already-authenticated.com',
            'key': 'key12345678',
            'published': False,
            'subject': 'Test Conversation',
            'created_ts': CloseToNow(),
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
            {
                'address': 'test@already-authenticated.com',
            }
        ]
    } == obj


async def test_add_message_participant(cli, pub_conv, url, get_conv):
    r = await cli.post(
        url('act', conv=pub_conv.key, component='message', verb='add', item='msg-secondmessagekey'),
        data='foobar',
        headers={
            'em2-auth': 'already-authenticated.com:123:whatever',
            'em2-actor': pub_conv.creator_address,
            'em2-timestamp': datetime.now().strftime('%s'),
            'em2-parent': 'pub-add-message-1234',
            'em2-action-key': 'x' * 20,
            'em2-msg-format': 'markdown',
        }
    )
    assert r.status == 201, await r.text()
    r = await cli.post(
        url('act', conv=pub_conv.key, component='participant', verb='add', item='foobar@example.com'),
        data='foobar',
        headers={
            'em2-auth': 'already-authenticated.com:123:whatever',
            'em2-actor': pub_conv.creator_address,
            'em2-timestamp': datetime.now().strftime('%s'),
            'em2-action-key': 'y' * 20,
        }
    )
    assert r.status == 201, await r.text()
    obj = await get_conv(pub_conv)
    assert {
        'actions': [
            {
                'actor': 'test@already-authenticated.com',
                'body': None,
                'component': None,
                'key': 'pub-add-message-1234',
                'message': 'msg-firstmessagekeyx',
                'parent': None,
                'participant': None,
                'timestamp': CloseToNow(),
                'verb': 'publish'
            },
            {
                'actor': 'test@already-authenticated.com',
                'body': 'foobar',
                'component': 'message',
                'key': 'xxxxxxxxxxxxxxxxxxxx',
                'message': 'msg-secondmessagekey',
                'parent': 'pub-add-message-1234',
                'participant': None,
                'timestamp': CloseToNow(),
                'verb': 'add'
            },
            {
                'actor': 'test@already-authenticated.com',
                'body': None,
                'component': 'participant',
                'key': 'yyyyyyyyyyyyyyyyyyyy',
                'message': None,
                'parent': None,
                'participant': 'foobar@example.com',
                'timestamp': CloseToNow(),
                'verb': 'add'
            },
        ],
        'details': {
            'creator': 'test@already-authenticated.com',
            'key': pub_conv.key,
            'published': True,
            'subject': 'Test Conversation',
            'created_ts': CloseToNow()
        },
        'messages': [
            {
                'deleted': False,
                'after': None,
                'body': 'this is the message',
                'format': 'markdown',
                'key': 'msg-firstmessagekeyx',
                'relationship': None,
            },
            {
                'deleted': False,
                'after': 'msg-firstmessagekeyx',
                'body': 'foobar',
                'format': 'markdown',
                'key': 'msg-secondmessagekey',
                'relationship': Relationships.SIBLING,
            }
        ],
        'participants': [
            {
                'address': 'test@already-authenticated.com',
            },
            {
                'address': 'foobar@example.com',
            }
        ]
    } == obj


async def test_wrong_conv(cli, conv, url):
    url_ = url('act', conv=conv.key, component='message', verb='add', item=conv.first_msg_key)
    r = await cli.post(url_, data='foobar', headers={
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'other@already-authenticated.com',
        'em2-timestamp': datetime.now().strftime('%s'),
        'em2-action-key': 'x' * 20,
    })
    assert r.status == 403, await r.text()
    assert await r.text() == '"other@already-authenticated.com" is not a participant in this conversation'


async def test_check_server(cli):
    r = await check_server(Settings(web_port=cli.server.port), expected_status=200)
    assert r == 0
    r = await check_server(Settings(web_port=cli.server.port + 1), expected_status=200)
    assert r == 1


async def test_no_headers(cli, url):
    r = await cli.post(url('act', conv='123', component='message', verb='add', item=''))
    assert r.status == 400, await r.text()
    assert 'header "em2-auth" missing' == await r.text()


async def test_bad_auth_token(cli, url):
    headers = {
        'em2-auth': '123',
        'em2-actor': 'test@example.com',
        'em2-timestamp': '123',
        'em2-action-key': '123',
    }

    r = await cli.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 403, await r.text()
    assert await r.text() == 'invalid token'


async def test_domain_mismatch(cli, url):
    headers = {
        'em2-auth': 'already-authenticated.com:123:whatever',
        'em2-actor': 'test@example.com',
        'em2-timestamp': str(to_unix_ms(datetime.now())),
        'em2-action-key': '123',
    }
    r = await cli.post(url('act', conv='123', component='message', verb='add', item=''), headers=headers)
    assert r.status == 403, await r.text()
    assert await r.text() == '"example.com" does not use "already-authenticated.com"'


async def test_authenticate(cli, url):
    headers = {
        'em2-platform': PLATFORM,
        'em2-timestamp': str(TIMESTAMP),
        'em2-signature': VALID_SIGNATURE
    }
    r = await cli.post(url('authenticate'), headers=headers)
    assert r.status == 201, await r.text()
    key = r.headers['em2-key']
    assert key.startswith('foobar.com:2461536000:')
    assert len(key) == 86


async def test_authenticate_wrong_fields(cli, url):
    headers = {
        'em2-platform': PLATFORM,
        'em2-timestamp': str(TIMESTAMP),
    }
    r = await cli.post(url('authenticate'), headers=headers)
    assert r.status == 400, await r.text()
    data = await r.json()
    assert [
        {
            'loc': [
                'em2-signature',
            ],
            'msg': 'field required',
            'type': 'value_error.missing',
        },
    ] == data


async def test_authenticate_failed(cli, url):
    headers = {
        'em2-platform': 'wham.com',
        'em2-timestamp': str(TIMESTAMP),
        'em2-signature': VALID_SIGNATURE
    }
    r = await cli.post(url('authenticate'), headers=headers)
    assert r.status == 400, await r.text()
    assert await r.text() == 'Authenticate failed: invalid signature'


async def test_index(cli, url):
    r = await cli.get(url('index'))
    assert r.status == 200, await r.text()
    data = await r.json()
    assert data['domain'] == 'em2.platform.example.com'
    assert data['interface'] == 'external'
