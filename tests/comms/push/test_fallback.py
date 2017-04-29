import os
from datetime import datetime

import pytest

from em2 import Settings
from em2.comms.fallback.aws import AwsFallbackHandler
from em2.core import Action, Components, Controller, Verbs, perms
from tests.fixture_classes import future_result, get_private_key_file


@pytest.yield_fixture
def fallback_ctrl_pusher(loop, reset_store):
    _ctrl = None

    async def _create(fallback_cls='em2.comms.fallback.FallbackHandler'):
        nonlocal _ctrl
        settings = Settings(
            LOCAL_DOMAIN='em2.local.com',
            PRIVATE_DOMAIN_KEY_FILE=get_private_key_file(),
            DATASTORE_CLS='tests.fixture_classes.SimpleDataStore',
            PUSHER_CLS='tests.fixture_classes.push.HttpMockedDNSPusher',
            FALLBACK_CLS=fallback_cls,
        )
        _ctrl = Controller(settings, loop=loop)
        _ctrl.pusher._concurrency_enabled = False
        await _ctrl.pusher.startup()
        async with await _ctrl.pusher.get_redis_conn() as redis:
            await redis.flushall()
        return _ctrl

    yield _create

    async def close():
        _ctrl and await _ctrl.pusher.shutdown()

    loop.run_until_complete(close())


async def test_no_mx(fallback_ctrl_pusher, mocker, caplog):
    mock_authenticate = mocker.patch('em2.comms.web.push.HttpDNSPusher.authenticate')

    ctrl = await fallback_ctrl_pusher()
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='foo bar', body='great body')

    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@fallback.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)  # conv id could have changed depending on milliseconds
    assert mock_authenticate.called is False
    assert 'Components.CONVERSATIONS . Verbs.ADD, from: sender@local.com, to: (1) receiver@fallback.com' in caplog


async def test_smtp_fallback(fallback_ctrl_pusher, mocker, loop):
    mock_authenticate = mocker.patch('em2.comms.web.push.HttpDNSPusher.authenticate')
    mock_send_message = mocker.patch('em2.comms.fallback.SmtpFallbackHandler.send_message')
    mock_send_message.return_value = future_result(loop, '123')

    ctrl = await fallback_ctrl_pusher('em2.comms.fallback.SmtpFallbackHandler')
    action = Action('sender@local.com', None, Verbs.ADD)
    conv_id = await ctrl.act(action, subject='the subject', body='x')

    a = Action('sender@local.com', conv_id, Verbs.ADD, Components.PARTICIPANTS)
    await ctrl.act(a, address='receiver@fallback.com', permissions=perms.WRITE)
    a = Action('sender@local.com', conv_id, Verbs.PUBLISH, Components.CONVERSATIONS)
    await ctrl.act(a)  # conv id could have changed depending on milliseconds
    conv_id = ctrl.ds.data[0]['conv_id']
    assert mock_authenticate.called is False
    mock_send_message.assert_called_with(
        bcc=[],
        e_from='sender@local.com',
        html_body='<p>x</p>\n\n\n'
                  '<p style="font-size:small;color:#666;">&mdash;<br>\n'
                  "You're participating in the em2 conversation %s. Reply to "
                  'this email to contribute to the conversation.<br>\n'
                  'You might consider upgrading to email 2.0 to get a greatly '
                  'improved email experience.</p>\n' % conv_id[:6],
        plain_body='x\n\n'
                   '--\n'
                   "You're participating in the em2 conversation %s. Reply to "
                   'this email to contribute to the conversation.\n'
                   'You might consider upgrading to email 2.0 to get a greatly '
                   'improved email experience.\n' % conv_id[:6],
        subject='the subject',
        to=['receiver@fallback.com']
    )


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
        FALLBACK_USERNAME='aws_access_key',
        FALLBACK_PASSWORD='aws_secret_key',
        FALLBACK_ENDPOINT='eu-west-1',
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
        plain_body='hello',
        html_body='<h1>hello</h1>',
    )
    assert mock_post.called
    assert mock_post.call_args[0] == ('https://email.eu-west-1.amazonaws.com/',)
    assert msg_id == '123'
    kwargs = mock_post.call_args[1]
    assert kwargs['timeout'] == 5
    assert kwargs['headers']['Content-Type'] == 'application/x-www-form-urlencoded'
    assert kwargs['headers']['X-Amz-Date'] == '20320101T000000Z'
    await fallback.close()


@pytest.mark.skipif(os.getenv('EM2_TEST_AWS_ACCESS_KEY') is None, reason='aws env vars not set')
async def test_aws_fallback_live(loop):
    settings = Settings(
        FALLBACK_USERNAME=os.environ['EM2_TEST_AWS_ACCESS_KEY'],
        FALLBACK_PASSWORD=os.environ['EM2_TEST_AWS_SECRET_KEY'],
        FALLBACK_ENDPOINT='eu-west-1',
    )

    fallback = AwsFallbackHandler(settings, loop=loop)
    await fallback.startup()
    msg_id = await fallback.send_message(
        e_from='testing@imber.io',
        to=['success@simulator.amazonses.com'],
        bcc=[],
        subject='the subject',
        plain_body='hello',
        html_body='<h1>hello</h1>',
    )
    assert len(msg_id) == 60
    await fallback.close()
