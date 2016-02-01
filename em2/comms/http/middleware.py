from aiohttp import web

from .utils import bad_request_response, logger, get_ip


async def auth_middleware_factory(app, handler):
    async def auth_middleware(request):
        log_extra = {'ip': get_ip(request)}
        if 'Authorization' not in request.headers:
            logger.info('bad request: %s', 'no auth header', extra=log_extra)
            return bad_request_response('No "Authorization" header found')

        token = request.headers['Authorization'].replace('Token ', '')
        platform = await check_token(token)
        if platform is None:
            logger.info('forbidden request: invalid token "%s"', token, extra=log_extra)
            return web.HTTPForbidden(body='Invalid Authorization token\n'.encode())
        request.platform = platform
        request.log_extra = log_extra
        return await handler(request)
    return auth_middleware


async def check_token(token):
    return True

middleware_factories = [auth_middleware_factory]
