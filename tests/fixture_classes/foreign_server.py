from aiohttp.web import Application, Response


async def auth(request):
    return Response(headers={'em2-key': f'foobar:{int(2e12)}:xyz'}, status=201)


async def act(request):
    return Response(status=201)


async def logging_middleware(app, handler):
    async def _handler(request):
        r = await handler(request)
        msg = f'{request.method} {request.path_qs} > {r.status}'
        # print(msg)
        request.app['request_log'].append(msg)
        return r
    return _handler


def create_test_app(loop):
    app = Application(middlewares=[logging_middleware])

    app.router.add_post('/authenticate', auth)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}', act, name='act')

    app.update(
        request_log=[]
    )
    return app
