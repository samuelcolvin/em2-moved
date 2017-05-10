from aiohttp.web_exceptions import HTTPForbidden
from cryptography.fernet import InvalidToken

from em2.db import set_recipient
from em2.utils.encoding import msg_decode


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


async def db_conn_middleware(app, handler):
    async def _handler(request):
        async with app['db'].acquire() as conn:
            request['conn'] = conn
            await set_recipient(request)
            # TODO save recipient_id in session
            return await handler(request)
    return _handler


middleware = (
    user_middleware,
    db_conn_middleware,
)
