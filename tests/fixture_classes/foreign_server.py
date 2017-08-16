from aiohttp.web import Application, Response, json_response
from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden, HTTPNotFound  # NOQA


async def auth(request):
    return Response(headers={'em2-key': f'foobar:{int(2e12)}:xyz'}, status=201)


CONV_DETAILS = {
    'details': {
        'creator': 'test@already-authenticated.com',
        'key': 'key12345678',
        'published': True,
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
            'readall': True
        },
        {
            'address': 'testing@local.com',
            'readall': False
        },
    ],
    'actions': [
        {
            'actor': 'test@already-authenticated.com',
            'body': None,
            'component': 'participant',
            'key': 'yyyyyyyyyyyyyyyyyyyy',
            'message': None,
            'parent': None,
            'participant': 'testing@local.com',
            'timestamp': '2032-06-01T13:00:00.12345',
            'verb': 'add'
        },
    ],
}


async def get(request):
    assert request.headers['em2-auth']
    participant = request.headers['em2-participant']
    assert participant == 'testing@local.com'
    if request.match_info['conv'] == 'key12345678':
        return json_response(CONV_DETAILS)
    else:
        raise HTTPNotFound()


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
