import json
from json import JSONDecodeError

from aiohttp import web

from em2.core.controller import Action
from em2.core.exceptions import Em2Exception
from .utils import bad_request_response, logger, json_bytes

async def act(request):
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
            return bad_request_response('Error Decoding JSON: {}'.format(e))

        if not isinstance(kwargs, dict):
            logger.info('bad request: kwargs not dict', extra=request.log_extra)
            return bad_request_response('request data is not a dictionary')

    actor = request.headers.get('Actor')
    if actor is None:
        logger.info('bad request: Actor missing', extra=request.log_extra)
        return bad_request_response('No "Actor" header found')

    action = Action(actor, conversation, verb, component, item)
    controller = request.app['controller']
    try:
        response = await controller.act(action, **kwargs)
    except Em2Exception as e:
        logger.info('Em2Exception: %r', e, extra=request.log_extra)
        return bad_request_response('{}: {}'.format(e.__class__.__name__, e))

    return web.Response(body=json_bytes(response, True), status=201, content_type='application/json')
