import hashlib
import hmac
import logging
import re
from binascii import hexlify
from datetime import datetime
from functools import reduce
from urllib.parse import urlencode

import aiohttp

from em2.exceptions import ConfigException, FallbackPushError

from . import SmtpFallbackHandler

logger = logging.getLogger('em2.fallback.ses')

_AWS_HOST = 'email.{region}.amazonaws.com'
_AWS_ENDPOINT = 'https://{host}/'
_AWS_SERVICE = 'ses'
_AWS_AUTH_REQUEST = 'aws4_request'
_CONTENT_TYPE = 'application/x-www-form-urlencoded'
_SIGNED_HEADERS = 'content-type', 'host', 'x-amz-date'
_CANONICAL_REQUEST = """\
POST
/

{canonical_headers}
{signed_headers}
{payload_hash}"""
_AUTH_ALGORITHM = 'AWS4-HMAC-SHA256'
_CREDENTIAL_SCOPE = '{date_stamp}/{region}/{service}/{auth_request}'
_STRING_TO_SIGN = """\
{algorithm}
{x_amz_date}
{credential_scope}
{canonical_request_hash}"""
_AUTH_HEADER = (
    '{algorithm} Credential={access_key}/{credential_scope},SignedHeaders={signed_headers},Signature={signature}'
)


class AwsFallbackHandler(SmtpFallbackHandler):
    """
    Fallback handler using AWS's SES service to send smtp emails.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        if None in {self.settings.FALLBACK_USERNAME, self.settings.FALLBACK_PASSWORD, self.settings.FALLBACK_ENDPOINT}:
            raise ConfigException('The following settings must be set to use AwsFallbackHandler: '
                                  'FALLBACK_USERNAME, FALLBACK_PASSWORD, FALLBACK_ENDPOINT')
        self.access_key = self.settings.FALLBACK_USERNAME
        self.secret_key_b = self.settings.FALLBACK_PASSWORD.encode()
        self.region = self.settings.FALLBACK_ENDPOINT
        self._host = _AWS_HOST.format(region=self.region)
        self._endpoint = _AWS_ENDPOINT.format(host=self._host)

    async def startup(self):
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def shutdown(self):
        self.session.close()

    @staticmethod
    def _now():
        return datetime.utcnow()

    def _aws_headers(self, data):
        n = self._now()
        x_amz_date = n.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = n.strftime('%Y%m%d')
        ctx = dict(
            access_key=self.access_key,
            algorithm=_AUTH_ALGORITHM,
            x_amz_date=x_amz_date,
            auth_request=_AWS_AUTH_REQUEST,
            content_type=_CONTENT_TYPE,
            date_stamp=date_stamp,
            host=self._host,
            payload_hash=hashlib.sha256(data).hexdigest(),
            region=self.region,
            service=_AWS_SERVICE,
            signed_headers=';'.join(_SIGNED_HEADERS),
        )
        ctx.update(
            credential_scope=_CREDENTIAL_SCOPE.format(**ctx),
        )
        canonical_headers = ''.join('{}:{}\n'.format(h, ctx[h.replace('-', '_')]) for h in _SIGNED_HEADERS)

        canonical_request = _CANONICAL_REQUEST.format(canonical_headers=canonical_headers, **ctx).encode()

        s2s = _STRING_TO_SIGN.format(canonical_request_hash=hashlib.sha256(canonical_request).hexdigest(), **ctx)
        key_parts = b'AWS4' + self.secret_key_b, date_stamp, self.region, _AWS_SERVICE, _AWS_AUTH_REQUEST, s2s
        signature = reduce(lambda key, msg: hmac.new(key, msg.encode(), hashlib.sha256).digest(), key_parts)

        authorization_header = _AUTH_HEADER.format(signature=hexlify(signature).decode(), **ctx)
        return {
            'Content-Type': _CONTENT_TYPE,
            'X-Amz-Date': x_amz_date,
            'Authorization': authorization_header
        }

    async def send_message(self, *, e_from, to, bcc, subject, plain_body, html_body):
        # TODO encode fields as per RFC 2822, perhaps already done by urlencode
        data = {
            'Action': 'SendEmail',
            'Source': e_from,
            'Message.Subject.Data': subject,
            'Message.Body.Text.Data': plain_body,
            'Message.Body.Html.Data': html_body,
        }
        data.update({'Destination.ToAddresses.member.{}'.format(i + 1): t.encode() for i, t in enumerate(to)})
        data.update({'Destination.BccAddresses.member.{}'.format(i + 1): t.encode() for i, t in enumerate(bcc)})
        data = urlencode(data).encode()

        headers = self._aws_headers(data)
        async with self.session.post(self._endpoint, data=data, headers=headers, timeout=5) as r:
            status_code = r.status
            text = await r.text()
        if status_code != 200:
            raise FallbackPushError('bad response {} != 200: {}'.format(r.status, text))
        msg_id = re.search('<MessageId>(.+?)</MessageId>', text)
        return msg_id.groups()[0]

    async def close(self):
        logger.info('closing http session')
        await self.session.close()
