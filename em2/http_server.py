import logging
import json
from json import JSONDecodeError

from aiohttp import web

from .base import Action
from .exceptions import Em2Exception

logger = logging.getLogger('http')


def bad_request_response(msg=''):
    msg += '\n'
    return web.HTTPBadRequest(body=msg.encode())


def json_bytes(data, pretty=False):
    if data is None:
        return b'\n'
    if pretty:
        s = json.dumps(data, indent=2) + '\n'
    else:
        s = json.dumps(data)
    return s.encode()


def get_ip(request):
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip


class Api:
    def __init__(self, app, em2_controller, url_root=''):
        self.app = app
        self.em2_ctrl = em2_controller
        self.add_routes(url_root)
        self.add_middleware()

    def add_routes(self, url_root):
        self.app.router.add_route('POST',
                                  url_root + '/{con:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}',
                                  self.event)

    def add_middleware(self):
        async def auth_middleware_factory(app, handler):
            async def auth_middleware(request):
                log_extra = {'ip': get_ip(request)}
                if 'Authorization' not in request.headers:
                    logger.info('bad request: %s', 'no auth header', extra=log_extra)
                    return bad_request_response('No "Authorization" header found')

                token = request.headers['Authorization'].replace('Token ', '')
                platform = await self.check_token(token)
                if platform is None:
                    logger.info('forbidden request: invalid token "%s"', token, extra=log_extra)
                    return web.HTTPForbidden(body='Invalid Authorization token\n'.encode())
                request.platform = platform
                request.log_extra = log_extra
                return await handler(request)
            return auth_middleware

        self.app._middlewares = [auth_middleware_factory]

    async def event(self, request):
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
            logger.info('bad request: Actor None', extra=request.log_extra)
            return bad_request_response('Actor not found in header')

        action = Action(actor, conversation, verb, component, item)
        try:
            response = await self.em2_ctrl.act(action, **kwargs)
        except Em2Exception as e:
            logger.info('Em2Exception: %r', e, extra=request.log_extra)
            return bad_request_response('{}: {}'.format(e.__class__.__name__, e))

        return web.Response(body=json_bytes(response, True), status=201, content_type='application/json')

    async def check_token(self, token):
        return True
