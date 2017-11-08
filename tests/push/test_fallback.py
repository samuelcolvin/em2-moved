import base64
import email
import json
import os
from asyncio import Future
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import pytest
from aiohttp.web_exceptions import HTTPUnauthorized

from em2 import Settings
from em2.core import ApplyAction, GetConv
from em2.fallback.aws import AwsFallbackHandler
from tests.conftest import CloseToNow, RegexStr


class MockPost:
    async def __aenter__(self):
        class Response:
            status = 200

            async def text(self):
                return 'fake response\n<MessageId>123</MessageId>'
        return Response()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


async def test_aws_fallback_mocked(mocker, loop):
    settings = Settings(
        fallback_username='aws_access_key',
        fallback_password='aws_secret_key',
        fallback_endpoint='eu-west-1',
    )
    fallback = AwsFallbackHandler(settings, loop=loop)
    await fallback.startup()
    mock_post = mocker.patch.object(fallback.session, 'post')
    mock_post.return_value = MockPost()
    mock_now = mocker.patch.object(fallback, '_now')
    mock_now.return_value = datetime(2032, 1, 1)

    e_msg = EmailMessage()
    e_msg['Subject'] = 'the subject'
    e_msg['From'] = 'from@local.com'
    e_msg['To'] = 'to@remote.com'
    e_msg.set_content('hello')
    e_msg.add_alternative('<p>hello</p>', subtype='html')

    msg_id = await fallback.send_message(
        e_from='from@local.com',
        to=['to@remote.com'],
        bcc=['bcc@remote.com'],
        email_msg=e_msg,
    )
    assert mock_post.called
    assert mock_post.call_args[0] == ('https://email.eu-west-1.amazonaws.com/',)
    assert msg_id == '123@eu-west-1.amazonses.com'
    kwargs = mock_post.call_args[1]
    assert kwargs['timeout'] == 5
    assert kwargs['headers']['Content-Type'] == 'application/x-www-form-urlencoded'
    assert kwargs['headers']['X-Amz-Date'] == '20320101T000000Z'
    await fallback.shutdown()


@pytest.mark.skipif(os.getenv('TEST_AWS_ACCESS_KEY') is None, reason='aws env vars not set')
async def test_aws_fallback_live(loop):
    settings = Settings(
        fallback_username=os.environ['TEST_AWS_ACCESS_KEY'],
        fallback_password=os.environ['TEST_AWS_SECRET_KEY'],
        fallback_endpoint='eu-west-1',
    )

    fallback = AwsFallbackHandler(settings, loop=loop)
    await fallback.startup()

    e_msg = EmailMessage()
    e_msg['Subject'] = 'the subject'
    e_msg['From'] = 'testing@imber.io'
    e_msg['To'] = 'success@simulator.amazonses.com'
    e_msg.set_content('hello')
    e_msg.add_alternative('<p>hello</p>', subtype='html')

    msg_id = await fallback.send_message(
        e_from='testing@imber.io',
        to=['success@simulator.amazonses.com'],
        bcc=[],
        email_msg=e_msg,
    )
    assert len(msg_id) == 84
    await fallback.shutdown()


async def add_recipient(conv, db_conn, address='testing@other.com'):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add--prt',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='participant',
        verb='add',
        item=address,
    )
    await apply_action.run()
    await db_conn.execute("""
    INSERT INTO action_states (action, ref, status) VALUES ($1, 'testing-message-id', 'successful')
    """, apply_action.action_id)


def create_message(in_reply_to):
    msg = email.message.EmailMessage()
    msg['Subject'] = 'testing'
    msg['From'] = 'testing@other.com'
    msg['To'] = 'testing@example.com'
    msg['Message-ID'] = '<foobar@sender.com>'
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
    n = datetime.now().astimezone(timezone(timedelta(hours=1)))
    msg['Date'] = email.utils.format_datetime(n)
    return msg


async def test_smtp_reply(cli, url, db_conn, conv):
    await add_recipient(conv, db_conn)

    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')

    msg = create_message('<testing-message-id>')
    msg.set_content('This is a plain test')
    msg.add_alternative('<p>This is a test</p>', subtype='html')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 2 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')

    msg = await db_conn.fetchrow('SELECT relationship, position, body FROM messages ORDER BY id DESC LIMIT 1')
    assert {
        'relationship': 'sibling',
        'position': [2],
        'body': '<p>\n This is a test\n</p>'
    } == dict(msg)


async def test_smtp_create(cli, url, db_conn):
    assert 0 == await db_conn.fetchval('SELECT COUNT(*) FROM conversations')

    msg = create_message(None)
    msg.set_content('hello EM2, this is SMTP')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM conversations')
    conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    json_str = await GetConv(db_conn).run(conv_key, 'testing@example.com', inc_states=True)
    conv_data = json.loads(json_str)
    assert {
        'details': {
            'key': conv_key,
            'subject': 'testing',
            'ts': CloseToNow(),
            'creator': 'testing@other.com',
            'published': True,
        },
        'messages': [
            {
                'key': RegexStr('msg-.*'),
                'after': None,
                'relationship': None,
                'body': 'hello EM2, this is SMTP',
                'format': 'markdown',
                'deleted': False,
            },
        ],
        'participants': [
            {
                'address': 'testing@example.com',
            },
            {
                'address': 'testing@other.com',
            },
        ],
        'actions': [
            {
                'key': RegexStr('smtp-.*'),
                'verb': 'publish',
                'component': None,
                'body': None,
                'ts': CloseToNow(),
                'actor': 'testing@other.com',
                'parent': None,
                'message': RegexStr('msg-.*'),
                'participant': None,
            },
        ],
        'action_states': [
            {
                'action': RegexStr('smtp-.*'),
                'ref': 'foobar@sender.com',
                'status': 'successful',
                'node': None,
                'errors': None,
            },
        ],
    } == conv_data


async def add_message(conv, db_conn, body='hello {key_no}', key_no=1):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key=f'act-testing-add-msg{key_no}',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='message',
        verb='add',
        body=body.format(key_no=key_no),
        parent='pub-add-message-1234'
    )
    await apply_action.run()
    email_id = f'testing-message-id-{key_no}'
    await db_conn.execute("""
    INSERT INTO action_states (action, ref, status) VALUES ($1, $2, 'successful')
    """, apply_action.action_id, email_id)
    return email_id, apply_action.item_key


async def test_gmail_smtp_reply(cli, url, db_conn, conv):
    await add_recipient(conv, db_conn)
    msg_id, message_key = await add_message(conv, db_conn)
    await add_message(conv, db_conn, key_no=2)

    assert 3 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')

    msg = create_message(f'<{msg_id}>')
    msg.add_alternative("""
    <p>This is a test</p>=
    <div class=3D"gmail_extra">=
        this is gmail extra content.=
    </div>""", subtype='html')
    msg_str = msg.as_string()
    # simpler than setting it in the EmailMessage
    msg_str = msg_str.replace('Content-Transfer-Encoding: 7bit\n', 'Content-Transfer-Encoding: quoted-printable\n')

    r = await cli.post(url('fallback-webhook'), data=msg_str)
    assert r.status == 204, await r.text()
    assert 4 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')

    msg = await db_conn.fetchrow("""
    SELECT m1.relationship AS relationship, m1.position AS position, m1.body AS body, m2.key AS after
    FROM messages as m1
    LEFT JOIN messages AS m2 ON m1.after = m2.id
    ORDER BY m1.id DESC
    LIMIT 1""")
    assert {
        'relationship': 'sibling',
        'position': [3],
        'body': '<p>\n This is a test\n</p>',
        'after': message_key,
    } == dict(msg)


async def test_smtp_em2_too(cli, url, db_conn, conv):
    await add_recipient(conv, db_conn)

    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')

    msg = create_message('<testing-message-id>')
    msg['EM2-ID'] = 'foobar'
    msg.set_content('This is a plain test')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM messages')


class MockRequest:
    def __init__(self, text, headers: dict=None):
        self._text = text
        self.headers = headers or {}

    async def text(self):
        return self._text


async def test_aws_receive_smtp(mocker, loop):
    settings = Settings(fallback_username='x', fallback_password='y', fallback_endpoint='z',
                        fallback_webhook_auth='foobar')
    fallback = AwsFallbackHandler(settings, loop=loop)

    process_smtp_message = mocker.patch.object(fallback, 'process_smtp_message')
    f = Future()
    f.set_result(None)
    process_smtp_message.return_value = f
    data = json.dumps({
        'Type': 'Notification',
        'Message': json.dumps({
            'content': base64.b64encode(b'test message body').decode(),
            'notificationType': 'Received'
        })
    })
    mock_request = MockRequest(data, headers={'Authorization': 'Basic Zm9vYmFyOg=='})
    await fallback.process_webhook(mock_request)
    process_smtp_message.assert_called_with('test message body')


async def test_aws_receive_smtp_no_auth(loop):
    settings = Settings(fallback_username='x', fallback_password='y', fallback_endpoint='z',
                        fallback_webhook_auth='foobar')
    fallback = AwsFallbackHandler(settings, loop=loop)

    with pytest.raises(HTTPUnauthorized):
        await fallback.process_webhook(MockRequest('x', headers={'Authorization': 'Basic XZm9vYmFyOg=='}))


async def test_aws_subscription_conf(loop, foreign_server):
    settings = Settings(fallback_username='x', fallback_password='y', fallback_endpoint='z',
                        fallback_webhook_auth='foobar')
    fallback = AwsFallbackHandler(settings, loop=loop)
    await fallback.startup()

    data = json.dumps({
        'Type': 'SubscriptionConfirmation',
        'SubscribeURL': f'http://localhost:{foreign_server.port}/'
    })
    mock_request = MockRequest(data, headers={'Authorization': 'Basic Zm9vYmFyOg=='})
    await fallback.process_webhook(mock_request)
    await fallback.shutdown()

    assert foreign_server.app['request_log'] == ['HEAD / > 200']


async def test_aws_receive_smtp_other_message(mocker, loop):
    settings = Settings(fallback_username='x', fallback_password='y', fallback_endpoint='z',
                        fallback_webhook_auth='foobar')
    fallback = AwsFallbackHandler(settings, loop=loop)

    process_smtp_message = mocker.patch.object(fallback, 'process_smtp_message')
    data = json.dumps({
        'Type': 'Notification',
        'Message': json.dumps({'notificationType': 'Other'})
    })
    mock_request = MockRequest(data, headers={'Authorization': 'Basic Zm9vYmFyOg=='})
    await fallback.process_webhook(mock_request)
    assert not process_smtp_message.called
