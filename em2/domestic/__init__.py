import base64

from aiohttp.web import Application
from cryptography.fernet import Fernet

from em2.core import Components, Verbs
from .views import Act, Create, Get, VList
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

    app.router.add_get('/', VList.view(), name='list')
    app.router.add_post('/new/', Create.view(), name='create')

    components = '|'.join(m.value for m in Components)
    verbs = '|'.join(m.value for m in Verbs)
    pattern = '/act/{conv:[a-z0-9]+}/{component:%s}/{verb:%s}/' % (components, verbs)
    app.router.add_post(pattern, Act.view(), name='act')

    app.router.add_get('/c/{conv:[a-z0-9]+}/', Get.view(), name='get')
    return app
