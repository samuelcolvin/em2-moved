from aiohttp.web import Application, Response

from . import Settings
from .domestic import create_domestic_app
from .foreign import create_foreign_app
from .version import VERSION


async def index(request):
    return Response(text=f'em2 v{VERSION} shared interface, domain: {request.app["settings"].LOCAL_DOMAIN}\n')


def create_app(settings: Settings=None):
    settings = settings or Settings()
    app = Application()
    app['settings'] = settings

    # TODO deal with domain routing
    app.router.add_get('/', index)

    foreign_app = create_foreign_app(settings)
    app.add_subapp('/f/', foreign_app)
    app['fapp'] = foreign_app

    domestic_app = create_domestic_app(settings)
    app.add_subapp('/d/', domestic_app)
    app['dapp'] = domestic_app
    return app
