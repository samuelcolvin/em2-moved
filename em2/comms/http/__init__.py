import asyncio
from aiohttp import web

from em2.core import Controller
from .push import HttpDNSPusher  # noqa
from .views import act, authenticate


async def startup(app):
    settings = app['settings']
    app.update(
        controller=Controller(settings=settings, loop=app.loop),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop)
    )
    await app['controller'].startup()
    await app['authenticator'].startup()


async def cleanup(app):
    await app['controller'].shutdown()
    await app['authenticator'].shutdown()


def create_app(*, settings, loop=None):
    loop = loop or asyncio.get_event_loop()
    app = web.Application(loop=loop)
    app['settings'] = settings

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)

    # TODO deal with domain routing
    app.router.add_route('POST', '/authenticate', authenticate)

    app.router.add_route('POST', '/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act)

    return app
