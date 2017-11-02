import asyncio
import logging
from time import time
from urllib.parse import urlencode

from aiohttp import ClientSession
from aiohttp.web import Application, Response, HTTPTemporaryRedirect
from cryptography.fernet import Fernet

from em2 import VERSION
from em2.core import Components, Verbs, gen_random, get_create_recipient
from em2.utils.web import (access_control_middleware, auth_middleware, db_conn_middleware, prepare_add_origin,
                           set_anon_views)
from .background import Background
from .views import Act, Create, Get, Publish, VList, Websocket

logger = logging.getLogger('em2.domestic')


async def index(request):
    s = request.app['settings']
    return Response(text=f'em2 v{VERSION}:{s.COMMIT or "-"} domestic interface\n')


async def app_startup(app):
    settings = app['settings']
    loop = app.loop or asyncio.get_event_loop()
    app.update(
        db=settings.db_cls(settings=settings, loop=loop),
        pusher=settings.pusher_cls(settings=settings, loop=loop),
        background=Background(app, loop),
        auth_client=ClientSession(loop=loop)
    )
    await app['db'].startup()
    await app['pusher'].log_redis_info(logger.debug)


async def app_cleanup(app):
    await app['auth_client'].close()
    await app['background'].close()
    await app['pusher'].close()
    await app['db'].close()


async def activate_session(request, data):
    session_token, created_at, user_address = data.split(':', 2)
    session_cache = 's:{}'.format(session_token).encode()
    expires_at = int(created_at) + request.app['settings'].cookie_grace_time
    async with await request.app['pusher'].get_redis_conn() as redis:
        data = await redis.get(session_cache)
        if data:
            recipient_id = int(data)
        elif expires_at > time():
            async with request.app['db'].acquire() as conn:
                recipient_id = await get_create_recipient(conn, user_address)
            await asyncio.gather(
                redis.set(session_cache, str(recipient_id).encode()),
                redis.expireat(session_cache, expires_at),
            )
        else:
            loc = request.app['settings'].auth_update_session_url + '?' + urlencode({'r': request.url})
            raise HTTPTemporaryRedirect(location=loc)
        request['session_args'] = recipient_id, user_address


def create_domestic_app(settings, app_name=None):
    app = Application(middlewares=(access_control_middleware, auth_middleware, db_conn_middleware))
    app.on_response_prepare.append(prepare_add_origin)

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.update(
        settings=settings,
        session_fernet=Fernet(settings.auth_session_secret),
        name=app_name or gen_random('d'),
        anon_views=set_anon_views('index'),
        activate_session=activate_session,
    )

    app.router.add_get('/list/', VList.view(), name='list')
    app.router.add_post('/create/', Create.view(), name='create')
    app.router.add_get('/ws/', Websocket.view(), name='websocket')
    conv_match = '{conv:[a-z0-9\-]{8,}}'
    app.router.add_post('/publish/%s/' % conv_match, Publish.view(), name='publish')

    components = '|'.join(m.value for m in Components)
    verbs = '|'.join(m.value for m in Verbs)
    pattern = '/act/%s/{component:%s}/{verb:%s}/' % (conv_match, components, verbs)
    app.router.add_post(pattern, Act.view(), name='act')

    app.router.add_get(r'/c/%s/' % conv_match, Get.view(), name='get')
    app.router.add_get('/', index, name='index')
    return app
