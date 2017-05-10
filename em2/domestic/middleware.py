from aiohttp.web_exceptions import HTTPForbidden
from cryptography.fernet import InvalidToken

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


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update is slightly ugly, but should happen vary rarely.
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def pg_conn_middleware(app, handler):
    async def _handler(request):
        async with app['pg'].acquire() as conn:
            request['conn'] = conn
            if not request.get('recipient_id'):
                recipient_id = await conn.fetchval(GET_RECIPIENT_ID, request['address'])
                if recipient_id is None:
                    recipient_id = await conn.fetchval(SET_RECIPIENT_ID, request['address'])
                request['recipient_id'] = recipient_id
                # TODO save recipient_id in session
            return await handler(request)
    return _handler


middleware = (
    user_middleware,
    pg_conn_middleware,
)
