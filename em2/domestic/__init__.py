import base64

from aiohttp.web import Application
from cryptography.fernet import Fernet

# from .views import retrieve_conv, retrieve_list
from .middleware import middleware


async def app_startup(app):
    app['controller'] = app['main']['controller']


def create_domestic_app(main_app):
    app = Application(middlewares=middleware)
    app.on_startup.append(app_startup)
    settings = main_app['settings']

    secret_key = base64.urlsafe_b64encode(settings.SECRET_KEY)
    app.update(
        settings=settings,
        main=main_app,
        fernet=Fernet(secret_key),
    )

    # app.router.add_get('/ret/list/', retrieve_list, name='retrieve-list')
    # app.router.add_get('/ret/{conv:[a-z0-9]+}/', retrieve_conv, name='retrieve-conv')
    return app
