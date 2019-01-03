import re

from aiohttp.web import Application, HTTPException, HTTPNotFound, Response, json_response, middleware


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
    key = request.headers['em2-action-key']
    m = re.search(r'error(\d{3})', key)
    if m:
        return Response(status=int(m.groups()[0]))
    else:
        return Response(status=201)


async def status(request):
    return Response(status=int(request.match_info['status']))


async def check_user_node(request):
    d = await request.json()
    domain = d['address'].split('@', 1)[-1]
    return json_response({'local': domain in {'example.com'}})


@middleware
async def logging_middleware(request, handler):
    try:
        r = await handler(request)
    except HTTPException as exc:
        request.app['request_log'].append(f'{request.method} {request.path_qs} > {exc.status}')
        raise
    else:
        request.app['request_log'].append(f'{request.method} {request.path_qs} > {r.status}')
        return r


def create_test_app():
    app = Application(middlewares=[logging_middleware])

    app.router.add_get('/', index)
    app.router.add_post('/auth/', auth)
    app.router.add_get('/get/{conv:[a-z0-9]+}/', get)
    app.router.add_post('/{conv:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:.*}', act)
    app.router.add_post('/create/{conv:[a-z0-9]+}/', create)
    app.router.add_route('*', r'/status/{status:\d+}/', status)
    app.router.add_get('/check-user-node/', check_user_node)

    app['request_log'] = []
    return app
