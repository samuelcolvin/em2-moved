"""
Views dedicated to propagation of data between platforms.
"""
import json
from json import JSONDecodeError

from aiohttp import web
from cerberus import Validator

from em2.core import Action
from em2.exceptions import Em2Exception, DomainPlatformMismatch, PlatformForbidden, FailedAuthentication
from em2.comms.logger import logger
from .utils import HTTPBadRequestStr, HTTPForbiddenStr, json_bytes, get_ip


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
    except FailedAuthentication as e:
        raise HTTPBadRequestStr(e.args[0]) from e
    return web.Response(body=json_bytes({'key': key}), status=201, content_type='application/json')


async def act(request):
    platform_token = request.headers.get('Authorization')
    if platform_token is None:
        raise HTTPBadRequestStr('No "Authorization" header found')
    platform_token = platform_token.replace('Token ', '')

    actor = request.headers.get('actor')
    if actor is None:
        raise HTTPBadRequestStr('No "Actor" header found')

    actor_domain = actor[actor.index('@') + 1:]
    auth = request.app['authenticator']
    try:
        await auth.check_domain_platform(actor_domain, platform_token)
    except PlatformForbidden as e:
        raise HTTPForbiddenStr('Invalid Authorization token') from e
    except DomainPlatformMismatch as e:
        raise HTTPForbiddenStr(e.args[0]) from e

    conversation = request.match_info['con']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    data = await request.text()
    kwargs = {}
    if data:
        try:
            kwargs = json.loads(data)
        except JSONDecodeError as e:
            raise HTTPBadRequestStr('Error Decoding JSON: {}'.format(e)) from e

        if not isinstance(kwargs, dict):
            raise HTTPBadRequestStr('request data is not a dictionary')
    action = Action(actor, conversation, verb, component, item)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **kwargs)
    except Em2Exception as e:
        raise HTTPBadRequestStr('{}: {}'.format(e.__class__.__name__, e))

    return web.Response(body=json_bytes(response, True), status=201, content_type='application/json')
