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
            'deleted': False,
            'after': None,
            'body': 'this is the message',
            'key': 'msg-firstmessagekeyx',
            'relationship': None
        }
    ],
    'participants': [
        {
            'address': 'test@already-authenticated.com',
        },
        {
            'address': 'testing@local.com',
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
            'ts': '2032-06-01T13:00:00.12345',
            'verb': 'add'
        },
    ],
}


async def index(request):
    return json_response({'status': 'ok'})


async def get(request):
    assert request.headers['em2-auth']
    participant = request.headers['em2-participant']
    assert participant == 'testing@local.com'
    if request.match_info['conv'] == 'key12345678':
        return json_response(CONV_DETAILS)
    else:
        raise HTTPNotFound()


async def create(request):
    return Response(status=204)


async def act(request):
    return Response(status=201)


async def logging_middleware(app, handler):
    async def _handler(request):
        try:
            r = await handler(request)
        except Exception as exc:
            request.app['request_log'].append(f'{request.method} {request.path_qs} > {exc.status}')
            raise
        else:
            # print(msg)
            request.app['request_log'].append(f'{request.method} {request.path_qs} > {r.status}')
            return r
    return _handler


def create_test_app(loop):
    app = Application(middlewares=[logging_middleware])

    app.router.add_get('/', index)
    app.router.add_post('/auth/', auth)
    app.router.add_get('/get/{conv:[a-z0-9]+}/', get)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:.*}', act)
    app.router.add_post('/create/{conv:[a-z0-9]+}/', create)

    app.update(
        request_log=[]
    )
    return app
