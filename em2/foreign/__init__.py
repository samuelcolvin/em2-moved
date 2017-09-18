import json
import logging
from aiohttp.web import Application, Response

from em2 import VERSION
from em2.utils.web import JSON_CONTENT_TYPE, db_conn_middleware
from .views import Act, Authenticate, Create, FallbackWebhook, Get

logger = logging.getLogger('em2.foreign')


async def index(request):
    s = request.app['settings']
    data = dict(
        description='em2 foreign interface',
        version=f'v{VERSION}',
        commit=s.COMMIT,
        interface='external',
        domain=s.EXTERNAL_DOMAIN
    )
    return Response(text=json.dumps(data, indent=2) + '\n', content_type=JSON_CONTENT_TYPE)


async def app_startup(app):
    settings = app['settings']
    db = settings.db_cls(settings=settings, loop=app.loop)
    pusher = settings.pusher_cls(settings=settings, loop=app.loop)
    app.update(
        db=db,
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop),
        pusher=pusher,
        fallback=settings.fallback_cls(settings=settings, loop=app.loop, db=db, pusher=pusher)
    )
    await db.startup()
    await pusher.log_redis_info(logger.debug)


async def app_cleanup(app):
    await app['db'].close()
    await app['authenticator'].close()
    await app['pusher'].close()


def create_foreign_app(settings):
    app = Application(middlewares=(db_conn_middleware,))
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.router.add_post('/auth/', Authenticate.view(), name='authenticate')
    app.router.add_get('/get/{conv:[a-z0-9]{8,}}/', Get.view(), name='get')
    app.router.add_post('/create/{conv:[a-z0-9]+}/', Create.view(), name='create')
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:.*}', Act.view(), name='act')
    app.router.add_post('/fallback-webhook/', FallbackWebhook.view(), name='fallback-webhook')
    app.router.add_get('/', index, name='index')
    return app
