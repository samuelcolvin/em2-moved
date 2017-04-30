from aiohttp.web import Application, Response

from . import Settings
from .comms.web import add_comms_routes
from .core import Controller
from .ui import create_ui_app
from .version import VERSION


async def app_startup(app):
    settings = app['settings']
    app.update(
        controller=Controller(settings=settings, loop=app.loop),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop)
    )
    await app['controller'].startup()
    await app['authenticator'].startup()


async def app_cleanup(app):
    await app['controller'].shutdown()
    await app['authenticator'].shutdown()


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
    # comms is implemented extra routes so it can be at the route
    add_comms_routes(app)

    # ui is implemented as a separate app as it needs it's own middleware and isn't served from "/"
    ui_app = create_ui_app(app)
    app.add_subapp('/ui/', ui_app)
    app['uiapp'] = ui_app
    return app
