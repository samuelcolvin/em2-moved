import json

from aiohttp import web


class HTTPBadRequestStr(web.HTTPBadRequest):
    def __init__(self, body):
        body += '\n'
        super().__init__(body=body.encode())


def json_bytes(data, pretty=False):
    if data is None:
        return b'\n'
    if pretty:
        s = json.dumps(data, indent=2) + '\n'
    else:
        s = json.dumps(data)
    return s.encode()


def get_ip(request):
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip
