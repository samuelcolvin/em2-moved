from aiohttp.web import Application

from . import Settings
from .protocol import create_protocol_app
from .ui import create_ui_app


def create_app(settings: Settings = None):
    settings = settings or Settings()
    app = Application()
    app['settings'] = settings

    # TODO deal with domain routing, perhaps nginx is enough
    ui_app = create_protocol_app(settings)
    app.add_subapp('/f/', ui_app)
    app['fapp'] = ui_app

    ui_app = create_ui_app(settings)
    app.add_subapp('/d/', ui_app)
    app['dapp'] = ui_app
    return app
