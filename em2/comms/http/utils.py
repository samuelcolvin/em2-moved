from aiohttp import web


class _StringException:
    def __init__(self, body):
        body += '\n'
        super().__init__(body=body.encode())


class HTTPBadRequestStr(_StringException, web.HTTPBadRequest):
    pass


class HTTPForbiddenStr(_StringException, web.HTTPForbidden):
    pass


def get_ip(request):
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip
