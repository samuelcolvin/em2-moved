from aiohttp.web import Application

from .views import act, authenticate


async def app_startup(app):
    settings = app['settings']
    app.update(
        db=settings.db_cls(app.loop, settings),
        authenticator=settings.authenticator_cls(settings=settings, loop=app.loop),
    )
    await app['db'].startup()
    await app['authenticator'].startup()


async def app_cleanup(app):
    await app['db'].close()
    await app['authenticator'].close()


def create_foreign_app(settings):
    app = Application()
    app['settings'] = settings

    app.on_startup.append(app_startup)
    app.on_cleanup.append(app_cleanup)

    # TODO deal with domain routing
    # TODO add trailing slashes
    app.router.add_post('/auth/', authenticate, name='authenticate')
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act, name='act')
    return app
