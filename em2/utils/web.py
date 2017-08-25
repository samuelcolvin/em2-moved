import datetime
import json
import traceback
from functools import update_wrapper
from typing import Type

from aiohttp.web import Application, HTTPBadRequest, HTTPForbidden, HTTPNotFound, Request, Response  # noqa
from asyncpg.connection import Connection  # noqa
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError

from .encoding import msg_decode

JSON_CONTENT_TYPE = 'application/json'


async def db_conn_middleware(app, handler):
    async def _handler(request):
        async with app['db'].acquire() as conn:
            request['conn'] = conn
            return await handler(request)
    return _handler


def decrypt_token(token: str, app: Application, model: Type[BaseModel]) -> BaseModel:
        try:
            raw_data = app['fernet'].decrypt(token.encode())
        except InvalidToken:
            raise HTTPForbidden(text='Invalid token')
        try:
            data = msg_decode(raw_data)
            return model(**data)
        except (ValueError, TypeError):
            raise HTTPBadRequest(text='bad cookie data')


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


class WebModel(BaseModel):
    def _process_values(self, values):
        try:
            return super()._process_values(values)
        except ValidationError as e:
            raise HTTPBadRequest(text=e.json(), content_type=JSON_CONTENT_TYPE)


async def _fetch404(func, sql, *args, msg=None):
    """
    fetch from the db, raise not found if the value is doesn't exist
    """
    val = await func(sql, *args)
    if not val:
        # TODO add debug
        msg = msg or 'unable to find value in db'
        tb = ''.join(traceback.format_stack())
        raise HTTPNotFound(text=f'{msg}\nsql:\n{sql}\ntraceback:{tb}')
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
            raise HTTPBadRequest(text=f'invalid request json: {e}')
        if not isinstance(data, dict):
            raise HTTPBadRequest(text='request json should be a dictionary')
        return data


class ViewMain(View):
    def __init__(self, request):
        super().__init__(request)
        from em2.push import Pusher
        self.pusher: Pusher = self.app['pusher']
