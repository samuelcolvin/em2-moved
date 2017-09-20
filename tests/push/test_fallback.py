import email
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

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

    msg_id = await fallback.send_message(
        e_from='from@local.com',
        to=['to@remote.com'],
        bcc=['bcc@remote.com'],
        subject='the subject',
        body='hello',
        action=type('Action', (), {'conv_key': 'testing', 'item': 'msg-test'}),
    )
    assert mock_post.called
    assert mock_post.call_args[0] == ('https://email.eu-west-1.amazonaws.com/',)
    assert msg_id == '123'
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
    msg_id = await fallback.send_message(
        e_from='testing@imber.io',
        to=['success@simulator.amazonses.com'],
        bcc=[],
        subject='the subject',
        body='hello',
        action=type('Action', (), {'conv_key': 'testing', 'item': 'msg-test'}),
    )
    assert len(msg_id) == 60
    await fallback.shutdown()


async def add_recipient(conv, db_conn, address='testing@other.com'):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add--prt',
        conv=conv.id,
        published=True,
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
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
    n = datetime.now().astimezone(timezone(timedelta(hours=1)))
    msg['Date'] = email.utils.format_datetime(n)
    return msg


async def test_smtp_reply(cli, url, db_conn, conv):
    await add_recipient(conv, db_conn)

    assert 1 == await db_conn.fetchval('SELECT count(*) FROM messages')

    msg = create_message('<testing-message-id>')
    msg.set_content('This is a plain test')
    msg.add_alternative('<p>This is a test</p>', subtype='html')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 2 == await db_conn.fetchval('SELECT count(*) FROM messages')

    msg = await db_conn.fetchrow('SELECT relationship, position, body FROM messages ORDER BY id DESC LIMIT 1')
    assert {
        'relationship': 'sibling',
        'position': [2],
        'body': '<p>\n This is a test\n</p>'
    } == dict(msg)


async def test_smtp_create(cli, url, db_conn):
    assert 0 == await db_conn.fetchval('SELECT count(*) FROM conversations')

    msg = create_message(None)
    msg.set_content('hello EM2, this is SMTP')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('SELECT count(*) FROM conversations')
    conv_key = await db_conn.fetchval('SELECT key FROM conversations')
    json_str = await GetConv(db_conn).run(conv_key, 'testing@example.com')
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
    } == conv_data


async def add_message(conv, db_conn, body='hello {key_no}', key_no=1):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key=f'act-testing-add-msg{key_no}',
        conv=conv.id,
        published=True,
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

    assert 3 == await db_conn.fetchval('SELECT count(*) FROM messages')

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
    assert 4 == await db_conn.fetchval('SELECT count(*) FROM messages')

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

    assert 1 == await db_conn.fetchval('SELECT count(*) FROM messages')

    msg = create_message('<testing-message-id>')
    msg['EM2-ID'] = 'foobar'
    msg.set_content('This is a plain test')

    r = await cli.post(url('fallback-webhook'), data=msg.as_string())
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('SELECT count(*) FROM messages')
