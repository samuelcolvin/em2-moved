"""
Views dedicated to propagation of data between platforms.
"""
import json
import logging

import pytz
from aiohttp import web
from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden
from cerberus import Validator

from em2.comms import encoding
from em2.core import Action
from em2.exceptions import DomainPlatformMismatch, Em2Exception, FailedInboundAuthentication, PlatformForbidden
from em2.utils import from_unix_ms
from em2.version import VERSION

logger = logging.getLogger('em2.comms.http')

# Note timestamp is an int here while it's a datetime elsewhere as it's an int when used in the signature
AUTHENTICATION_SCHEMA = {
    'platform': {'type': 'string', 'required': True},
    'timestamp': {'type': 'integer', 'required': True, 'min': 0},
    'signature': {'type': 'string', 'required': True},
}

CT_JSON = 'application/json'


def get_ip(request):
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip


async def index(request):
    domain = request.app['settings'].LOCAL_DOMAIN
    return web.Response(text=f'em2 v{VERSION} HTTP api, domain: {domain}', content_type='text/plain')


async def authenticate(request):
    logger.info('authentication request from %s', get_ip(request))

    body_data = await request.read()
    try:
        obj = encoding.decode(body_data)
    except ValueError as e:
        logger.info('bad request: invalid msgpack data')
        raise HTTPBadRequest(text='error decoding data: {}\n'.format(e)) from e

    logger.info('authentication data: %s', obj)
    v = Validator(AUTHENTICATION_SCHEMA)
    if not v(obj):
        raise HTTPBadRequest(text=json.dumps(v.errors, sort_keys=True) + '\n', content_type=CT_JSON)

    auth = request.app['authenticator']
    try:
        key = await auth.authenticate_platform(obj['platform'], obj['timestamp'], obj['signature'])
    except FailedInboundAuthentication as e:
        logger.info('failed inbound authentication: %s', e)
        raise HTTPBadRequest(text=e.args[0] + '\n') from e
    return web.Response(body=encoding.encode({'key': key}), status=201, content_type=encoding.MSGPACK_CONTENT_TYPE)


# headers and whether they're required
EM2_HEADERS = [
    ('auth', True),
    ('address', True),
    ('timestamp', True),
    ('event_id', True),
    ('parent_event_id', False),
    ('timezone', False),
]


def _get_headers(request_headers):
    em2_headers = {}
    errors = []
    for h, required in EM2_HEADERS:
        name = 'em2-' + h.replace('_', '-')
        v = request_headers.get(name, None)
        if v:
            em2_headers[h] = v
        elif required:
            errors.append(name)

    if errors:
        raise HTTPBadRequest(text='Missing Headers: {}'.format(', '.join(errors)) + '\n', content_type=CT_JSON)
    return em2_headers


async def _parse_headers(headers, auth):
    platform_token = headers.pop('auth')
    try:
        platform = await auth.valid_platform_token(platform_token)
    except PlatformForbidden as e:
        raise HTTPForbidden(text='Invalid auth header\n') from e

    logger.info('action from %s', platform)
    address = headers.pop('address')
    address_domain = address[address.index('@') + 1:]
    try:
        await auth.check_domain_platform(address_domain, platform)
    except DomainPlatformMismatch as e:
        raise HTTPForbidden(text=e.args[0] + '\n') from e

    timezone = headers.pop('timezone', 'utc')
    try:
        timezone = pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError as e:
        raise HTTPBadRequest(text=f'Unknown timezone "{timezone}"\n') from e

    timestamp = headers.pop('timestamp')
    try:
        timestamp = from_unix_ms(int(timestamp)).replace(tzinfo=timezone)
    except ValueError as e:
        raise HTTPBadRequest(text=f'Invalid timestamp "{timestamp}"\n') from e
    return address, timestamp, timezone, headers


async def act(request):
    headers = _get_headers(request.headers)
    address, timestamp, timezone, extra_headers = await _parse_headers(headers, request.app['authenticator'])

    # TODO support json as well as msgpack
    body_data = await request.read()
    try:
        obj = encoding.decode(body_data, tz=timezone)
    except ValueError as e:
        raise HTTPBadRequest(text='Error Decoding msgpack: {}\n'.format(e)) from e

    if not isinstance(obj, dict):
        raise HTTPBadRequest(text='request data is not a dictionary\n')

    conversation = request.match_info['conv']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    action = Action(address, conversation, verb, component, item=item, timestamp=timestamp, **extra_headers)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **obj)
    except Em2Exception as e:
        raise HTTPBadRequest(text='{}: {}\n'.format(e.__class__.__name__, e))

    body = encoding.encode(response) if response else b'\n'
    return web.Response(body=body, status=201, content_type=encoding.MSGPACK_CONTENT_TYPE)
