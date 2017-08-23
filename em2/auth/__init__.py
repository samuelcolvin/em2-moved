import asyncio
import logging

from aiohttp.web import Application, Response
from cryptography.fernet import Fernet

from em2 import VERSION

logger = logging.getLogger('em2.auth')


async def index(request):
    s = request.app['settings']
    return Response(text=f'em2 v{VERSION}:{s.COMMIT or "-"} auth interface\n')


async def app_startup(app):
    settings = app['settings']
    loop = app.loop or asyncio.get_event_loop()
    app.update(
        db=settings.db_cls(settings=settings, loop=loop),
    )
    await app['db'].startup()


async def app_cleanup(app):
    await app['db'].close()


def create_auth_app(settings):
    app = Application()

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.update(
        settings=settings,
        fernet=Fernet(settings.SECRET_SESSION_KEY),
    )

    app.router.add_get('/', index, name='index')
    return app
