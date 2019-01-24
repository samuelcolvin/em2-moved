import asyncio
import logging

import bcrypt
from aiohttp import ClientSession, ClientTimeout
from aiohttp.web import Application, Response
from arq import create_pool_lenient
from cryptography.fernet import Fernet

from em2 import VERSION, Settings
from em2.utils.web import (access_control_middleware, auth_middleware, db_conn_middleware, prepare_add_origin,
                           set_anon_views)
from .sessions import activate_session
from .view import (AcceptInvitationView, AccountView, CheckUserNodeView, LoginView, LogoutView, SessionsView,
                   UpdateSession)

logger = logging.getLogger('em2.auth')


async def index(request):
    s = request.app['settings']
    return Response(text=f'em2 v{VERSION}:{s.COMMIT or "-"} auth interface\n')


CREATE_NODE_SQL = """
  INSERT INTO auth_nodes (domain) VALUES ($1)
  ON CONFLICT (domain) DO UPDATE SET domain=EXCLUDED.domain RETURNING id
"""


async def app_startup(app):
    settings: Settings = app['settings']
    loop = asyncio.get_event_loop()
    app.update(
        db=settings.db_cls(settings=settings, loop=loop),
        session=ClientSession(loop=loop, timeout=ClientTimeout(total=10)),
        redis=await create_pool_lenient(settings.redis_redis, loop),
    )
    await app['db'].startup()
    async with app['db'].acquire() as conn:
        # TODO this is a hack until proper multi-node support is implemented.
        app['default_node_id'] = await conn.fetchval(CREATE_NODE_SQL, settings.EXTERNAL_DOMAIN)


async def app_cleanup(app):
    await app['db'].close()
    await app['session'].close()

    app['redis'].close()
    await app['redis'].wait_closed()


def create_auth_app(settings: Settings):
    app = Application(middlewares=(access_control_middleware, auth_middleware, db_conn_middleware))
    app.on_response_prepare.append(prepare_add_origin)

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.update(
        settings=settings,
        session_fernet=Fernet(settings.auth_session_secret),
        invitation_fernet=Fernet(settings.auth_invitation_secret),
        # used for password checks with address is invalid
        alt_pw_hash=bcrypt.hashpw('x'.encode(), bcrypt.gensalt(settings.auth_bcrypt_work_factor)).decode(),
        anon_views=set_anon_views('index', 'login', 'accept-invitation', 'check-user-node'),
        activate_session=activate_session,
    )

    app.router.add_get('/', index, name='index')
    app.router.add_get('/check-user-node/', CheckUserNodeView.view(), name='check-user-node')
    app.router.add_route('*', '/update-session/', UpdateSession.view(), name='update-session')
    app.router.add_route('*', '/login/', LoginView.view(), name='login')
    app.router.add_post('/logout/', LogoutView.view(), name='logout')
    app.router.add_get('/account/', AccountView.view(), name='account')
    app.router.add_get('/sessions/', SessionsView.view(), name='sessions')
    app.router.add_route('*', '/accept-invitation/', AcceptInvitationView.view(), name='accept-invitation')
    return app
