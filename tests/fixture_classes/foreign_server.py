from aiohttp.web import Application, Response, json_response


async def auth(request):
    return Response(headers={'em2-key': f'foobar:{int(2e12)}:xyz'}, status=201)


CONV_DETAILS = {
    'actions': None,
    'details': {
        'creator': 'test@already-authenticated.com',
        'key': 'key123',
        'published': False,
        'subject': 'Test Conversation',
        'ts': '2032-06-01T12:00:00.12345'
    },
    'messages': [
        {
            'active': True,
            'after': None,
            'body': 'this is the message',
            'key': 'msg-firstmessagekeyx',
            'relationship': None
        }
    ],
    'participants': [
        {
            'address': 'test@already-authenticated.com',
            'readall': False
        }
    ]
}


async def get(request):
    return json_response(CONV_DETAILS)


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
    app.router.add_get('/get/{conv:[a-z0-9]+}/', get)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:.*}', act)

    app.update(
        request_log=[]
    )
    return app
