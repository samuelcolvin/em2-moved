from aiohttp.web import HTTPBadRequest, HTTPForbidden
from cryptography.fernet import InvalidToken

from em2.core import get_create_recipient
from em2.utils.encoding import msg_decode, msg_encode
from em2.utils.web import db_conn_middleware

from .common import Session

# TODO enforce Same-Origin, json Content-Type, Referrer and XSS rules


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


async def update_session_middleware(app, handler):
    async def _handler(request):
        update_session = not bool(request['session'].recipient_id)
        if update_session:
            recipient_id = await get_create_recipient(request['conn'], request['session'].address)
            request['session'].recipient_id = recipient_id

        response = await handler(request)

        if update_session:
            data = msg_encode(request['session'].values())
            token = app['fernet'].encrypt(data).decode()
            # TODO set cookie domain?
            response.set_cookie(app['settings'].COOKIE_NAME, token, secure=not app['settings'].DEBUG, httponly=True)

        return response
    return _handler


middleware = (
    user_middleware,
    db_conn_middleware,
    update_session_middleware,
)
