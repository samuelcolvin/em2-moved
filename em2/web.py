from aiohttp.web import Application

from . import Settings
from .domestic import create_domestic_app
from .foreign import create_foreign_app


def create_app(settings: Settings=None):
    settings = settings or Settings()
    app = Application()
    app['settings'] = settings

    # TODO deal with domain routing, perhaps nginx is enough
    foreign_app = create_foreign_app(settings)
    app.add_subapp('/f/', foreign_app)
    app['fapp'] = foreign_app

    domestic_app = create_domestic_app(settings)
    app.add_subapp('/d/', domestic_app)
    app['dapp'] = domestic_app
    return app
