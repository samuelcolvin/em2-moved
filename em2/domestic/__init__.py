import asyncio
import logging

from aiohttp.web import Application
from cryptography.fernet import Fernet

from em2.core import Components, Verbs, gen_random
from .background import Background
from .middleware import middleware
from .views import Act, Create, Get, Publish, VList, Websocket

logger = logging.getLogger('em2.domestic')


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

    app.router.add_get('/', VList.view(), name='list')
    app.router.add_post('/new/', Create.view(), name='create')
    app.router.add_get('/ws/', Websocket.view(), name='websocket')
    app.router.add_post('/publish/{conv:[a-z0-9]+}/', Publish.view(), name='publish')

    components = '|'.join(m.value for m in Components)
    verbs = '|'.join(m.value for m in Verbs)
    pattern = '/act/{conv:[a-z0-9]+}/{component:%s}/{verb:%s}/' % (components, verbs)
    app.router.add_post(pattern, Act.view(), name='act')

    app.router.add_get('/c/{conv:[a-z0-9]+}/', Get.view(), name='get')
    return app
