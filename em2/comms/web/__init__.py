from .views import act, authenticate


def add_comms_routes(app):
    # TODO deal with domain routing
    # TODO add trailing slashes
    app.router.add_post('/authenticate', authenticate)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act)
