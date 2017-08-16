import logging
from aiohttp.web import Application

from em2.utils.web import db_conn_middleware
from .views import Act, Authenticate, Get

logger = logging.getLogger('em2.foreign')


async def app_startup(app):
    settings = app['settings']
    app.update(
        db=settings.db_cls(settings=settings, loop=app.loop),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop),
        pusher=settings.pusher_cls(settings=settings, loop=app.loop, ref='foreign'),
    )
    await app['db'].startup()
    await app['pusher'].log_redis_info(logger.info)


async def app_cleanup(app):
    await app['db'].close()
    await app['authenticator'].close()
    await app['pusher'].close()


def create_foreign_app(settings):
    app = Application(middlewares=(db_conn_middleware,))
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    # TODO deal with domain routing
    app.router.add_post('/auth/', Authenticate.view(), name='authenticate')
    app.router.add_get('/get/{conv:[a-z0-9]{8,}}/', Get.view(), name='get')
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:.*}', Act.view(), name='act')
    return app
