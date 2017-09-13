import os
from datetime import datetime

import pytest

from em2 import Settings
from em2.fallback.aws import AwsFallbackHandler


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
