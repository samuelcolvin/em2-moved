from em2.core import get_create_recipient
from em2.utils.encoding import msg_encode
from em2.utils.web import db_conn_middleware, decrypt_token

from .common import Session

# TODO enforce Same-Origin, json Content-Type, Referrer and XSS rules


async def user_middleware(app, handler):
    async def user_middleware_handler(request):
        # index can be viewed without auth
        if request.match_info.route.name not in ('index', 'index-head'):
            token = request.cookies.get(app['settings'].cookie_name, '')
            request['session'] = decrypt_token(token, app, Session)
        return await handler(request)
    return user_middleware_handler


async def update_session_middleware(app, handler):
    secure_cookies = app['settings'].secure_cookies

    async def _handler(request):
        session = request.get('session')
        update_session = session and not bool(session.recipient_id)
        if update_session:
            recipient_id = await get_create_recipient(request['conn'], request['session'].address)
            request['session'].recipient_id = recipient_id

        response = await handler(request)

        if update_session:
            data = msg_encode(request['session'].values())
            token = app['fernet'].encrypt(data).decode()
            response.set_cookie(app['settings'].cookie_name, token, secure=secure_cookies, httponly=True)

        return response
    return _handler


middleware = (
    user_middleware,
    db_conn_middleware,
    update_session_middleware,
)
