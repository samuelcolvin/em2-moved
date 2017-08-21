import asyncio
import logging

from aiohttp.web import Application, Response
from cryptography.fernet import Fernet

from em2 import VERSION
from em2.core import Components, Verbs, gen_random
from .background import Background
from .middleware import middleware
from .views import Act, Create, Get, Publish, VList, Websocket

logger = logging.getLogger('em2.domestic')


async def index(request):
    return Response(text=f'em2 v{VERSION} domestic interface, domain: {request.app["settings"].DOMESTIC_DOMAIN}\n')


async def app_startup(app):
    settings = app['settings']
    loop = app.loop or asyncio.get_event_loop()
    app.update(
        db=settings.db_cls(settings=settings, loop=loop),
        pusher=settings.pusher_cls(settings=settings, loop=loop, ref='domestic'),
        background=Background(app, loop),
    )
    await app['db'].startup()
    await app['pusher'].log_redis_info(logger.info)


async def app_cleanup(app):
    await app['background'].close()
    await app['pusher'].close()
    await app['db'].close()


def create_domestic_app(settings, app_name=None):
    app = Application(middlewares=middleware)

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.update(
        settings=settings,
        fernet=Fernet(settings.SECRET_SESSION_KEY),
        name=app_name or gen_random('d'),
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
