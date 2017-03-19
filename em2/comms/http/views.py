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


ACT_SCHEMA = {
    'address': {'type': 'string', 'required': True, 'empty': False},
    'timestamp': {'type': 'datetime', 'required': True},
    'event_id': {'type': 'string', 'required': True, 'empty': False},
    'parent_event_id': {'type': 'string', 'required': False},
    'data': {'type': 'dict', 'required': False},
}


async def _check_token(request):
    platform_token = request.headers.get('Authorization')
    if platform_token is None:
        raise HTTPBadRequest(text='No "Authorization" header found\n')
    platform_token = platform_token.replace('Token ', '')

    auth = request.app['authenticator']
    try:
        platform = await auth.valid_platform_token(platform_token)
    except PlatformForbidden as e:
        raise HTTPForbidden(text='Invalid Authorization token\n') from e
    else:
        return auth, platform


async def act(request):
    auth, platform = await _check_token(request)
    logger.info('action from %s', platform)

    body_data = await request.read()

    try:
        timezone = pytz.timezone(request.headers.get('timezone', 'utc'))
    except pytz.UnknownTimeZoneError as e:
        raise HTTPBadRequest(text=e.args[0] + '\n') from e

    try:
        obj = encoding.decode(body_data, tz=timezone)
    except ValueError as e:
        raise HTTPBadRequest(text='Error Decoding msgpack: {}\n'.format(e)) from e

    if not isinstance(obj, dict):
        raise HTTPBadRequest(text='request data is not a dictionary\n')

    v = Validator(ACT_SCHEMA)
    if not v(obj):
        raise HTTPBadRequest(text=json.dumps(v.errors, sort_keys=True) + '\n', content_type=CT_JSON)

    address = obj['address']
    address_domain = address[address.index('@') + 1:]
    try:
        await auth.check_domain_platform(address_domain, platform)
    except DomainPlatformMismatch as e:
        raise HTTPForbidden(text=e.args[0] + '\n') from e

    conversation = request.match_info['conv']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    action = Action(address, conversation, verb, component, item=item, timestamp=obj['timestamp'],
                    event_id=obj['event_id'], parent_event_id=obj.get('parent_event_id'))
    controller = request.app['controller']
    try:
        response = await controller.act(action, **obj.pop('data', {}))
    except Em2Exception as e:
        raise HTTPBadRequest(text='{}: {}\n'.format(e.__class__.__name__, e))

    body = encoding.encode(response) if response else b'\n'
    return web.Response(body=body, status=201, content_type=encoding.MSGPACK_CONTENT_TYPE)
