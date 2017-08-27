import asyncio
import logging

import bcrypt
from aiohttp import ClientSession
from aiohttp.web import Application, Response
from arq import create_pool_lenient
from cryptography.fernet import Fernet

from em2 import VERSION, Settings
from em2.utils.web import auth_middleware, db_conn_middleware
from .sessions import activate_session
from .view import AcceptInvitationView, AccountView, LoginView, LogoutView, SessionsView, UpdateSession

logger = logging.getLogger('em2.auth')


async def index(request):
    s = request.app['settings']
    return Response(text=f'em2 v{VERSION}:{s.COMMIT or "-"} auth interface\n')


async def app_startup(app):
    settings: Settings = app['settings']
    loop = app.loop or asyncio.get_event_loop()
    app.update(
        db=settings.db_cls(settings=settings, loop=loop),
        session=ClientSession(loop=loop, read_timeout=5, conn_timeout=5),
        redis_pool=await create_pool_lenient(settings.auth_redis, loop),
    )
    await app['db'].startup()


async def app_cleanup(app):
    await app['db'].close()
    await app['session'].close()

    app['redis_pool'].close()
    await app['redis_pool'].wait_closed()
    await app['redis_pool'].clear()


def create_auth_app(settings: Settings):
    app = Application(middlewares=(auth_middleware, db_conn_middleware,))

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.update(
        settings=settings,
        fernet=Fernet(settings.auth_token_key),
        # used for password checks with address is invalid
        alt_pw_hash=bcrypt.hashpw('x'.encode(), bcrypt.gensalt(settings.auth_bcrypt_work_factor)).decode(),
        anon_views=['index', 'login', 'accept-invitation'],
        activate_session=activate_session,
    )

    app.router.add_get('/', index, name='index')
    app.router.add_route('*', '/update-session/', UpdateSession.view(), name='update-session')
    app.router.add_route('*', '/login/', LoginView.view(), name='login')
    app.router.add_post('/logout/', LogoutView.view(), name='logout')
    app.router.add_get('/account/', AccountView.view(), name='account')
    app.router.add_get('/sessions/', SessionsView.view(), name='sessions')
    app.router.add_route('*', '/accept-invitation/', AcceptInvitationView.view(), name='accept-invitation')
    return app
