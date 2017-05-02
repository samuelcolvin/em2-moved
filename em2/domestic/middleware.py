from aiohttp.web_exceptions import HTTPForbidden
from cryptography.fernet import InvalidToken

from em2.utils import msg_decode


async def user_middleware(app, handler):
    async def user_middleware_handler(request):
        token = request.cookies.get(app['settings'].COOKIE_NAME, '')
        try:
            data = app['fernet'].decrypt(token.encode())
        except InvalidToken:
            raise HTTPForbidden(text='Invalid token')

        session = msg_decode(data)
        request.update(session)
        return await handler(request)
    return user_middleware_handler


middleware = (
    user_middleware,
)
