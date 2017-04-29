from aiohttp import web

from em2 import Settings
from em2.core import Controller
from .push import HttpDNSPusher  # noqa
from .views import act, authenticate, index


async def app_startup(app):
    settings = app['settings']
    app.update(
        controller=Controller(settings=settings, loop=app.loop),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop)
    )
    await app['controller'].startup()
    await app['authenticator'].startup()


async def app_cleanup(app):
    await app['controller'].shutdown()
    await app['authenticator'].shutdown()


def create_app(*, settings: Settings=None):
    settings = settings or Settings()
    app = web.Application()
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    # TODO deal with domain routing
    app.router.add_get('/', index)
    app.router.add_post('/authenticate', authenticate)

    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act)

    return app
