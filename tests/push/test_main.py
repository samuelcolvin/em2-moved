from em2.core import ApplyAction
from tests.conftest import RegexStr


async def test_add_participant_foreign(mocked_pusher, db_conn, conv, foreign_server):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add-mess',
        conv=conv.id,
        published=True,
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


async def test_add_participant_fallback(mocked_pusher, db_conn, conv):
    apply_action = ApplyAction(
        db_conn,
        remote_action=False,
        action_key='act-testing-add-mess',
        conv=conv.id,
        published=True,
        actor=await db_conn.fetchval('SELECT id FROM recipients'),
        component='participant',
        verb='add',
        item='testing@other.com',
    )
    await apply_action.run()
    assert len(mocked_pusher.fallback.messages) == 0
    await mocked_pusher.push.direct(apply_action.action_id)

    assert len(mocked_pusher.fallback.messages) == 1
    m = mocked_pusher.fallback.messages[0]
    action = m.pop('action')
    assert action.conv_key == 'key12345678'
    assert {
        'e_from': 'testing@example.com',
        'to': ['testing@other.com'],
        'bcc': [],
        'subject': 'Test Conversation',
        'body': 'adding testing@other.com to the conversation',
    } == m
