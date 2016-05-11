"""
Views dedicated to propagation of data between platforms.
"""
import json
from json import JSONDecodeError

from aiohttp import web

from em2.core import Action
from em2.exceptions import Em2Exception
from em2.comms.logger import logger
from .utils import HTTPBadRequestStr, json_bytes, get_ip


async def get_platform(request):
    if 'Authorization' not in request.headers:
        logger.info('bad request: %s', 'no auth header', extra=request.log_extra)
        raise HTTPBadRequestStr('No "Authorization" header found')

    token = request.headers['Authorization'].replace('Token ', '')
    platform = await check_token(token)
    if platform is None:
        logger.info('forbidden request: invalid token "%s"', token, extra=request.log_extra)
        raise web.HTTPForbidden(body=b'Invalid Authorization token\n')
    return platform


async def check_token(token):
    return True


async def act(request):
    request.log_extra = {'ip': get_ip(request)}
    platform = await get_platform(request)
    logger.info('act request from %s', platform, extra=request.log_extra)

    conversation = request.match_info['con']
    component = request.match_info['component']
    verb = request.match_info['verb']
    item = request.match_info['item'] or None

    data = await request.content.read()
    data = data.decode()
    kwargs = {}
    if data:
        try:
            kwargs = json.loads(data)
        except JSONDecodeError as e:
            logger.info('bad request: invalid json', extra=request.log_extra)
            raise HTTPBadRequestStr('Error Decoding JSON: {}'.format(e))

        if not isinstance(kwargs, dict):
            logger.info('bad request: kwargs not dict', extra=request.log_extra)
            raise HTTPBadRequestStr('request data is not a dictionary')

    actor = request.headers.get('Actor')
    if actor is None:
        logger.info('bad request: Actor missing', extra=request.log_extra)
        raise HTTPBadRequestStr('No "Actor" header found')

    action = Action(actor, conversation, verb, component, item)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **kwargs)
    except Em2Exception as e:
        logger.info('Em2Exception: %r', e, extra=request.log_extra)
        raise HTTPBadRequestStr('{}: {}'.format(e.__class__.__name__, e))

    return web.Response(body=json_bytes(response, True), status=201, content_type='application/json')
