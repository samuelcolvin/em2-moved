"""
Views dedicated to propagation of data between platforms.
"""
import json

import pytz
from aiohttp import web
from cerberus import Validator

from em2.comms import encoding
from em2.comms.logger import logger
from em2.core import Action
from em2.exceptions import DomainPlatformMismatch, Em2Exception, FailedInboundAuthentication, PlatformForbidden

from .utils import HTTPBadRequestStr, HTTPForbiddenStr, get_ip

# Note timestamp is in int here while it's a datetime as it's an int when used in the signature
AUTHENTICATION_SCHEMA = {
    'platform': {'type': 'string', 'required': True},
    'timestamp': {'type': 'integer', 'required': True, 'min': 0},
    'signature': {'type': 'string', 'required': True},
}

async def authenticate(request):
    logger.info('authentication request from %s', get_ip(request))

    body_data = await request.read()
    try:
        obj = encoding.decode(body_data)
    except ValueError as e:
        logger.info('bad request: invalid msgpack data')
        raise HTTPBadRequestStr('error decoding data: {}'.format(e)) from e

    v = Validator(AUTHENTICATION_SCHEMA)
    if not v(obj):
        raise HTTPBadRequestStr(json.dumps(v.errors, sort_keys=True))

    auth = request.app['authenticator']
    try:
        key = await auth.authenticate_platform(obj['platform'], obj['timestamp'], obj['signature'])
    except FailedInboundAuthentication as e:
        raise HTTPBadRequestStr(e.args[0]) from e
    return web.Response(body=encoding.encode({'key': key}), status=201, content_type=encoding.MSGPACK_CONTENT_TYPE)


ACT_SCHEMA = {
    'address': {'type': 'string', 'required': True, 'empty': False},
    'timestamp': {'type': 'datetime', 'required': True},
    'event_id': {'type': 'string', 'required': True, 'empty': False},
    'parent_event_id': {'type': 'string', 'required': False},
    'kwargs': {'type': 'dict', 'required': False},
}


async def _check_token(request):
    platform_token = request.headers.get('Authorization')
    if platform_token is None:
        raise HTTPBadRequestStr('No "Authorization" header found')
    platform_token = platform_token.replace('Token ', '')

    auth = request.app['authenticator']
    try:
        platform = await auth.valid_platform_token(platform_token)
    except PlatformForbidden as e:
        raise HTTPForbiddenStr('Invalid Authorization token') from e
    else:
        return auth, platform


async def act(request):
    auth, platform = await _check_token(request)

    body_data = await request.read()

    try:
        timezone = pytz.timezone(request.headers.get('timezone', 'utc'))
    except pytz.UnknownTimeZoneError as e:
        raise HTTPBadRequestStr(e.args[0]) from e

    try:
        obj = encoding.decode(body_data, tz=timezone)
    except ValueError as e:
        raise HTTPBadRequestStr('Error Decoding msgpack: {}'.format(e)) from e

    if not isinstance(obj, dict):
        raise HTTPBadRequestStr('request data is not a dictionary')

    v = Validator(ACT_SCHEMA)
    if not v(obj):
        raise HTTPBadRequestStr(json.dumps(v.errors, sort_keys=True))

    address = obj.pop('address')
    address_domain = address[address.index('@') + 1:]
    try:
        await auth.check_domain_platform(address_domain, platform)
    except DomainPlatformMismatch as e:
        raise HTTPForbiddenStr(e.args[0]) from e

    conversation = request.match_info['conv']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    timestamp = obj.pop('timestamp')

    kwargs = obj.pop('kwargs', {})
    action = Action(address, conversation, verb, component, item=item, timestamp=timestamp,
                    event_id=obj['event_id'], parent_event_id=obj.get('parent_event_id'))
    controller = request.app['controller']
    try:
        response = await controller.act(action, **kwargs)
    except Em2Exception as e:
        raise HTTPBadRequestStr('{}: {}'.format(e.__class__.__name__, e))

    body = encoding.encode(response) if response else b'\n'
    return web.Response(body=body, status=201, content_type=encoding.MSGPACK_CONTENT_TYPE)
