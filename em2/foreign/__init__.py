from aiohttp.web import Application

from .views import act, authenticate


async def app_startup(app):
    settings = app['settings']
    app.update(
        # controller=Controller(settings=settings, loop=app.loop),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop)
    )
    # await app['controller'].startup()
    await app['authenticator'].startup()


async def app_cleanup(app):
    # await app['controller'].shutdown()
    await app['authenticator'].close()


def create_foreign_app(settings):
    app = Application()
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    # TODO deal with domain routing
    # TODO add trailing slashes
    app.router.add_post('/authenticate', authenticate)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act)
    return app
