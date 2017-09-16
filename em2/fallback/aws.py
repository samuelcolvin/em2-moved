import base64
import hashlib
import hmac
import json
import logging
import re
from binascii import hexlify
from datetime import datetime
from email.message import EmailMessage
from functools import reduce
from secrets import compare_digest
from typing import List
from urllib.parse import urlencode

import aiohttp
from aiohttp.web_exceptions import HTTPBadRequest, HTTPUnauthorized

from em2.core import Action
from em2.exceptions import ConfigException, FallbackPushError

from . import FallbackHandler

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


class AwsFallbackHandler(FallbackHandler):
    """
    Fallback handler using AWS's SES service to send smtp emails.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        if None in {self.settings.fallback_username, self.settings.fallback_password, self.settings.fallback_endpoint}:
            raise ConfigException('The following settings must be set to use AwsFallbackHandler: '
                                  'fallback_username, fallback_password, fallback_endpoint')
        self.access_key = self.settings.fallback_username
        self.secret_key_b = self.settings.fallback_password.encode()
        self.region = self.settings.fallback_endpoint
        self._host = _AWS_HOST.format(region=self.region)
        self._endpoint = _AWS_ENDPOINT.format(host=self._host)
        if self.settings.fallback_webhook_auth:
            pw = self.settings.fallback_webhook_auth
            if b':' not in pw:
                pw += b':'
            self.auth_header = f'Basic {base64.b64encode(pw).decode()}'
        else:
            self.auth_header = None

    async def startup(self):
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def shutdown(self):
        await self.session.close()

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

    async def send_message(self, *, e_from: str, to: List[str], bcc: List[str], subject: str, body: str,
                           action: Action):

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = e_from
        msg['To'] = ','.join(to)
        msg['EM2-ID'] = action.conv_key + ':' + action.item
        msg.set_content(self.plain_format(body, action.conv_key))
        msg.add_alternative(self.html_format(body, action.conv_key), subtype='html')

        data = {
            'Action': 'SendRawEmail',
            'Source': e_from,
            'RawMessage.Data': base64.b64encode(msg.as_string().encode())
        }
        data.update({f'Destination.ToAddresses.member.{i + 1}': t.encode() for i, t in enumerate(to)})
        data.update({f'Destination.BccAddresses.member.{i + 1}': t.encode() for i, t in enumerate(bcc)})
        data = urlencode(data).encode()

        headers = self._aws_headers(data)
        async with self.session.post(self._endpoint, data=data, headers=headers, timeout=5) as r:
            status_code = r.status
            text = await r.text()
        if status_code != 200:
            raise FallbackPushError(f'bad response {r.status} != 200: {text}')
        msg_id = re.search('<MessageId>(.+?)</MessageId>', text)
        return msg_id.groups()[0]

    @staticmethod
    def _decode_json(s: str, description: str):
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            raise HTTPBadRequest(text=f'invalid json in {description}')

    async def process_webhook(self, request):
        if self.auth_header and not compare_digest(self.auth_header, request.headers.get('Authorization', '')):
            raise HTTPUnauthorized(text='invalid auth header')
        # content type is plain text for SNS, so we have to decode json manually
        # see https://forums.aws.amazon.com/thread.jspa?threadID=69413, we also have to decode json twice :-(
        # TODO catch more errors here, eg. missing 'content'
        data = self._decode_json(await request.text(), 'body')
        # TODO check X-SES-Spam-Verdict, X-SES-Virus-Verdict from data['headers']
        message = self._decode_json(data.get('Message'), 'Message')
        smtp_content = base64.b64decode(message['content']).decode()
        await self.process_smtp_message(smtp_content)
