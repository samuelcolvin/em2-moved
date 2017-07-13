from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden
from cryptography.fernet import InvalidToken

from em2.utils.encoding import msg_decode, msg_encode

from .common import Session


async def user_middleware(app, handler):
    async def user_middleware_handler(request):
        token = request.cookies.get(app['settings'].COOKIE_NAME, '')
        try:
            raw_data = app['fernet'].decrypt(token.encode())
        except InvalidToken:
            raise HTTPForbidden(text='Invalid token')
        try:
            data = msg_decode(raw_data)
            request['session'] = Session(**data)
        except (ValueError, TypeError):
            raise HTTPBadRequest(text='bad cookie data')
        return await handler(request)
    return user_middleware_handler


async def db_conn_middleware(app, handler):
    async def _handler(request):
        async with app['db'].acquire() as conn:
            request['conn'] = conn
            return await handler(request)
    return _handler


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update is slightly ugly, but should happen vary rarely.
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def set_recipient(request):
    if request['session'].recipient_id:
        return
    recipient_id = await request['conn'].fetchval(GET_RECIPIENT_ID, request['session'].address)
    if recipient_id is None:
        recipient_id = await request['conn'].fetchval(SET_RECIPIENT_ID, request['session'].address)
    request['session'].recipient_id = recipient_id
    request['session_change'] = True


async def update_session_middleware(app, handler):
    async def _handler(request):
        await set_recipient(request)
        response = await handler(request)

        if request.get('session_change'):
            data = msg_encode(request['session'].values())
            token = app['fernet'].encrypt(data).decode()
            response.set_cookie(app['settings'].COOKIE_NAME, token)

        return response
    return _handler


middleware = (
    user_middleware,
    db_conn_middleware,
    update_session_middleware,
)
