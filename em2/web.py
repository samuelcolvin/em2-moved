from aiohttp.web import Application, Response

from . import Settings
from .domestic import create_domestic_app
from .foreign import create_foreign_app
from .version import VERSION


async def app_startup(app):
    pass
    # settings = app['settings']
    # app.update(
    #     controller=Controller(settings=settings, loop=app.loop),
    #     authenticator=settings.authenticator_cls(settings=settings, loop=app.loop)
    # )
    # await app['controller'].startup()
    # await app['authenticator'].startup()


async def app_cleanup(app):
    pass
    # await app['controller'].shutdown()
    # await app['authenticator'].shutdown()


async def index(request):
    domain = request.app['settings'].LOCAL_DOMAIN
    return Response(text=f'em2 v{VERSION} HTTP api, domain: {domain}\n')


def create_app(settings: Settings=None):
    settings = settings or Settings()
    app = Application()
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    app.router.add_get('/', index)

    foreign_app = create_foreign_app(app)
    app.add_subapp('/f/', foreign_app)
    app['fapp'] = foreign_app

    domestic_app = create_domestic_app(app)
    app.add_subapp('/d/', domestic_app)
    app['dapp'] = domestic_app
    return app
