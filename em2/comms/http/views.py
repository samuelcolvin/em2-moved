"""
Views dedicated to propagation of data between platforms.
"""
import json
from json import JSONDecodeError

import pytz
from aiohttp import web
from cerberus import Validator

from em2.comms.logger import logger
from em2.core import Action
from em2.exceptions import DomainPlatformMismatch, Em2Exception, FailedInboundAuthentication, PlatformForbidden
from em2.utils import from_unix_timestamp

from .utils import HTTPBadRequestStr, HTTPForbiddenStr, get_ip, json_bytes

AUTHENTICATION_SCHEMA = {
    'platform': {'type': 'string', 'required': True},
    'timestamp': {'type': 'integer', 'required': True, 'min': 0},
    'signature': {'type': 'string', 'required': True},
}

async def authenticate(request):
    logger.info('authentication request from %s', get_ip(request))
    try:
        obj = await request.json()
    except JSONDecodeError as e:
        logger.info('bad request: invalid json')
        raise HTTPBadRequestStr('Error Decoding JSON: {}'.format(e)) from e

    v = Validator(AUTHENTICATION_SCHEMA)
    if not v(obj):
        raise HTTPBadRequestStr(json.dumps(v.errors, sort_keys=True))

    auth = request.app['authenticator']
    try:
        key = await auth.authenticate_platform(obj['platform'], obj['timestamp'], obj['signature'])
    except FailedInboundAuthentication as e:
        raise HTTPBadRequestStr(e.args[0]) from e
    return web.Response(body=json_bytes({'key': key}), status=201, content_type='application/json')


ACT_SCHEMA = {
    'address': {'type': 'string', 'required': True, 'empty': False},
    'timestamp': {'type': 'integer', 'required': True, 'min': 0},
    'event_id': {'type': 'string', 'required': True, 'empty': False},
    'timezone': {'type': 'string', 'required': False},
    'item': {'type': 'string', 'required': False},
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

    try:
        body_data = await request.json()
    except JSONDecodeError as e:
        raise HTTPBadRequestStr('Error Decoding JSON: {}'.format(e)) from e

    if not isinstance(body_data, dict):
        raise HTTPBadRequestStr('request data is not a dictionary')

    v = Validator(ACT_SCHEMA)
    if not v(body_data):
        raise HTTPBadRequestStr(json.dumps(v.errors, sort_keys=True))

    address = body_data.pop('address')
    address_domain = address[address.index('@') + 1:]
    try:
        await auth.check_domain_platform(address_domain, platform)
    except DomainPlatformMismatch as e:
        raise HTTPForbiddenStr(e.args[0]) from e

    conversation = request.match_info['conv']
    component = request.match_info['component']
    verb = request.match_info['verb']

    timestamp = from_unix_timestamp(body_data.pop('timestamp')).replace(tzinfo=pytz.utc)
    try:
        timezone = pytz.timezone(body_data.pop('timezone', 'utc'))
    except pytz.UnknownTimeZoneError as e:
        raise HTTPBadRequestStr(e.args[0]) from e

    timestamp = timestamp.astimezone(timezone)
    kwargs = body_data.pop('kwargs', {})
    action = Action(address, conversation, verb, component, timestamp=timestamp, **body_data)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **kwargs)
    except Em2Exception as e:
        raise HTTPBadRequestStr('{}: {}'.format(e.__class__.__name__, e))

    return web.Response(body=json_bytes(response, True), status=201, content_type='application/json')
