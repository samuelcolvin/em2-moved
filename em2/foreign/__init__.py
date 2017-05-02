from aiohttp.web import Application

from .views import act, authenticate


def create_foreign_app(main_app):
    app = Application()
    app['settings'] = main_app['settings']
    # TODO deal with domain routing
    # TODO add trailing slashes
    app.router.add_post('/authenticate', authenticate)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act)
    return app
