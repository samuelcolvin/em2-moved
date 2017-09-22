import json

from em2.core import ApplyAction, GetConv
from em2.fallback import get_email_body
from tests.conftest import CloseToNow, RegexStr


async def test_add_participant_foreign(mocked_pusher, db_conn, conv, foreign_server):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add--prt',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='participant',
        verb='add',
        item='testing@foreign.com',
    )
    await apply_action.run()
    await mocked_pusher.push.direct(apply_action.action_id)

    assert foreign_server.app['request_log'] == [
        'POST /auth/ > 201',
        RegexStr('POST /key12345678/participant/add/testing@foreign.com > 201'),
    ]


async def test_push_failure(mocked_pusher, db_conn, conv, foreign_server):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-error500-add-prt',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='participant',
        verb='add',
        item='testing@foreign.com',
    )
    await apply_action.run()
    await mocked_pusher.push.direct(apply_action.action_id)

    assert foreign_server.app['request_log'] == [
        'POST /auth/ > 201',
        RegexStr('POST /key12345678/participant/add/testing@foreign.com > 500'),
    ]
    json_str = await GetConv(db_conn).run(conv.key, 'testing@example.com', inc_states=True)
    conv_data = json.loads(json_str)
    assert [
        {
            'action': 'act-error500-add-prt',
            'ref': None,
            'status': 'failed',
            'node': f'em2.platform.foreign.com:{foreign_server.port}',
            'errors': [
                {
                    'ts': CloseToNow(),
                    'error': 'bad response: 500',
                    'stage': 'post',
                },
            ],
        },
    ] == conv_data['action_states']


async def add_prt(db_conn, conv):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add--prt',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='participant',
        verb='add',
        item='testing@other.com',
    )
    await apply_action.run()
    return apply_action


async def test_add_participant_fallback(mocked_pusher, db_conn, conv):
    apply_action = await add_prt(db_conn, conv)
    assert len(mocked_pusher.fallback.messages) == 0
    await mocked_pusher.push.direct(apply_action.action_id)

    assert len(mocked_pusher.fallback.messages) == 1
    m = mocked_pusher.fallback.messages[0]
    email_msg = m.pop('email_msg')
    assert email_msg['Subject'] == 'Test Conversation'
    body, is_html = get_email_body(email_msg)
    assert is_html is False
    assert 'adding testing@other.com to the conversation' in body
    assert 'key12345678' in email_msg['EM2-ID']
    assert {
        'e_from': 'testing@example.com',
        'to': ['testing@other.com'],
        'bcc': [],
    } == m


async def test_publish_fallback(mocked_pusher, db_conn, draft_conv):
    await add_prt(db_conn, draft_conv)
    action_id = await db_conn.fetchval("""
        INSERT INTO actions (key, conv, actor, verb, message)
        SELECT 'pub-add-message-1234', $1, $2, 'publish', m.id
        FROM messages as m
        WHERE m.conv = $1
        LIMIT 1
        RETURNING id
        """, draft_conv.id, await db_conn.fetchval('SELECT id FROM recipients'))
    assert len(mocked_pusher.fallback.messages) == 0

    await mocked_pusher.push.direct(action_id)

    assert len(mocked_pusher.fallback.messages) == 1
    m = mocked_pusher.fallback.messages[0]
    email_msg = m.pop('email_msg')
    assert email_msg['Subject'] == 'Test Conversation'
    assert email_msg['In-Reply-To'] is None
    assert email_msg['References'] is None
    body, is_html = get_email_body(email_msg)
    assert is_html
    assert '<p>this is the message</p>' in body
    assert 'key12345678' in email_msg['EM2-ID']
    assert {
        'e_from': 'testing@example.com',
        'to': ['testing@other.com'],
        'bcc': [],
    } == m


async def test_reply_fallback(mocked_pusher, db_conn, conv):
    apply_action = await add_prt(db_conn, conv)
    await db_conn.execute("""
    INSERT INTO action_states (action, ref, status)
    VALUES ($1, 'testing-references@other.com', 'successful')
    """, apply_action.action_id)

    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add-mess',
        conv=conv.id,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='message',
        verb='add',
        body='this is a test message',
        parent=await db_conn.fetchval('SELECT key FROM actions WHERE message IS NOT NULL'),
    )
    await apply_action.run()
    await db_conn.execute("""
    INSERT INTO action_states (action, ref, status)
    VALUES ($1, 'testing-in-reply-to@other.com', 'successful')
    """, apply_action.action_id)

    assert len(mocked_pusher.fallback.messages) == 0

    await mocked_pusher.push.direct(apply_action.action_id)

    assert len(mocked_pusher.fallback.messages) == 1
    m = mocked_pusher.fallback.messages[0]
    email_msg = m.pop('email_msg')
    assert email_msg['Subject'] == 'Test Conversation'
    assert email_msg['In-Reply-To'] == '<testing-in-reply-to@other.com>'
    assert email_msg['References'] == '<testing-in-reply-to@other.com> <testing-references@other.com>'
