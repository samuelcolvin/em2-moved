import base64

from aiohttp.web import Application
from cryptography.fernet import Fernet

from .views import retrieve_list
from .middleware import middleware


def create_ui_app(main_app):
    app = Application(middlewares=middleware)

    secret_key = base64.urlsafe_b64encode(main_app['settings'].SECRET_KEY)
    app.update(
        settings=main_app['settings'],
        main=main_app,
        fernet=Fernet(secret_key),
    )

    app.router.add_get('/list/', retrieve_list)
    # app.router.add_get('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/', retrieve_details)
    return app
