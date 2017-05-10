import base64

from aiohttp.web import Application
from cryptography.fernet import Fernet

from .views import retrieve_conv, retrieve_list
from .middleware import middleware


async def app_startup(app):
    settings = app['settings']
    app.update(
        db=settings.db_cls(app.loop, settings),
    )
    await app['db'].startup()


async def app_cleanup(app):
    await app['db'].close()


def create_domestic_app(settings):
    app = Application(middlewares=middleware)

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    secret_key = base64.urlsafe_b64encode(settings.SECRET_KEY)
    app.update(
        settings=settings,
        fernet=Fernet(secret_key),
    )

    app.router.add_get('/l/', retrieve_list, name='retrieve-list')
    app.router.add_get('/d/{conv:[a-z0-9]+}/', retrieve_conv, name='retrieve-conv')
    return app
