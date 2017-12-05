import datetime
import json
import logging
import traceback
from functools import update_wrapper

from aiohttp import web_exceptions
from aiohttp.hdrs import METH_OPTIONS, METH_POST
from aiohttp.web import Application, Request, Response, middleware  # noqa
from asyncpg.connection import Connection  # noqa
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError

JSON_CONTENT_TYPE = 'application/json'
logger = logging.getLogger('em2.utils')


class _JsonHTTPError:
    def __init__(self, **data):
        super().__init__(text=json.dumps(data), content_type=JSON_CONTENT_TYPE)


class JsonError:
    class HTTPBadRequest(_JsonHTTPError, web_exceptions.HTTPBadRequest):
        pass

    class HTTPUnauthorized(_JsonHTTPError, web_exceptions.HTTPUnauthorized):
        pass

    class HTTPForbidden(_JsonHTTPError, web_exceptions.HTTPForbidden):
        pass

    class HTTPNotFound(_JsonHTTPError, web_exceptions.HTTPNotFound):
        pass

    class HTTPConflict(_JsonHTTPError, web_exceptions.HTTPConflict):
        pass

    class HTTPTooManyRequests(_JsonHTTPError, web_exceptions.HTTPTooManyRequests):
        pass

    class HTTPInternalServerError(_JsonHTTPError, web_exceptions.HTTPInternalServerError):
        pass


class WebModel(BaseModel):
    def _process_values(self, values):
        try:
            return super()._process_values(values)
        except ValidationError as e:
            raise web_exceptions.HTTPBadRequest(text=e.json(), content_type=JSON_CONTENT_TYPE)

    class Config:
        allow_extra = False


@middleware
async def db_conn_middleware(request, handler):
    async with request.app['db'].acquire() as conn:
        request['conn'] = conn
        return await handler(request)


def set_anon_views(*anon_views):
    anon_views = set(anon_views)
    anon_views |= {v + '-head' for v in anon_views}
    return frozenset(anon_views)


@middleware
async def auth_middleware(request, handler):
    if request.match_info.route.name not in request.app['anon_views']:
        cookie = request.cookies.get(request.app['settings'].cookie_name, '')
        try:
            token = request.app['session_fernet'].decrypt(cookie.encode())
        except InvalidToken:
            raise JsonError.HTTPUnauthorized(error='cookie missing or invalid')
        await request.app['activate_session'](request, token.decode())

    return await handler(request)


@middleware
async def access_control_middleware(request, handler):
    if request.method == METH_OPTIONS:
        if (request.headers.get('Access-Control-Request-Method') == METH_POST and
                request.headers.get('Access-Control-Request-Headers').lower() == 'content-type' and
                request.headers.get('Origin') == request.app['settings'].ORIGIN_DOMAIN):
            return Response(body=b'ok')
        else:
            raise JsonError.HTTPForbidden(error='Access-Control checks failed')
    # TODO check origin, referrer, and Content-Type
    return await handler(request)


async def prepare_add_origin(request, response):
    response.headers.update({
        'Access-Control-Allow-Origin': request.app['settings'].ORIGIN_DOMAIN,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Headers': 'Content-Type',
    })


def get_ip(request):
    header = request.app['settings'].client_ip_header
    if header:
        ips = request.headers.get(header)
        if not ips:
            raise JsonError.HTTPBadRequest(error=f'missing header "{header}"')
        return ips.split(',', 1)[0]
    else:
        peername = request.transport.get_extra_info('peername')
        return peername[0] if peername else '-'


class Em2JsonEncoder(json.JSONEncoder):
    # add more only when necessary
    ENCODER_BY_TYPE = {
        # this should match postgres serialisation of datetimes
        datetime.datetime: lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%S.%f'),
    }

    def default(self, obj):
        try:
            encoder = self.ENCODER_BY_TYPE[type(obj)]
        except KeyError:
            return super().default(obj)
        return encoder(obj)


def json_response(*, status_=200, list_=None, **data):
    return Response(
        body=json.dumps(data if list_ is None else list_, cls=Em2JsonEncoder).encode(),
        status=status_,
        content_type=JSON_CONTENT_TYPE,
    )


def raw_json_response(text: str, *, status_=200):
    return Response(
        text=text,
        status=status_,
        content_type=JSON_CONTENT_TYPE,
    )


async def _fetch404(func, sql, *args, msg=None):
    """
    fetch from the db, raise not found if the value is doesn't exist
    """
    val = await func(sql, *args)
    if not val:
        # TODO add debug
        msg = msg or 'unable to find value in db'
        tb = ''.join(t for t in traceback.format_stack()[:-1] if '/em2/em2/' in t)
        logger.error('%s\nsql:\n%s\nargs:\n  %s\ntraceback:\n%s', msg, sql, args, tb)
        raise JsonError.HTTPNotFound(error=msg)
    return val


class FetchOr404Mixin:
    async def fetchval404(self, sql, *args, msg=None):
        return await _fetch404(self.conn.fetchval, sql, *args, msg=msg)

    async def fetchrow404(self, sql, *args, msg=None):
        return await _fetch404(self.conn.fetchrow, sql, *args, msg=msg)


class View(FetchOr404Mixin):
    def __init__(self, request):
        self.request: Request = request
        self.app: Application = request.app
        self.conn: Connection = request['conn']
        from em2 import Settings
        self.settings: Settings = self.app['settings']

    @classmethod
    def view(cls):

        async def view(request):
            self = cls(request)
            return await self.call(request)

        view.view_class = cls

        # take name and docstring from class
        update_wrapper(view, cls, updated=())

        # and possible attributes set by decorators
        update_wrapper(view, cls.call, assigned=())
        return view

    async def call(self, request):
        raise NotImplementedError()

    async def request_json(self):
        try:
            data = await self.request.json()
        except ValueError as e:
            raise JsonError.HTTPBadRequest(error=f'invalid request json: {e}')
        if not isinstance(data, dict):
            raise JsonError.HTTPBadRequest(error='request json should be a dictionary')
        return data


class ViewMain(View):
    def __init__(self, request):
        super().__init__(request)
        from em2.push import Pusher
        self.pusher: Pusher = self.app['pusher']
