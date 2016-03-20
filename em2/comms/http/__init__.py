import asyncio
from aiohttp import web

from .propagation import act


async def finish_controller(app):
    ctrl = app['controller']
    await ctrl.ds.finish()


def create_app(controller, loop=None, url_root=''):
    loop = loop or asyncio.get_event_loop()
    app = web.Application(loop=loop)
    app['controller'] = controller

    app.register_on_finish(finish_controller)

    url = url_root + '/{con:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}'
    app.router.add_route('POST', url, act)

    return app
