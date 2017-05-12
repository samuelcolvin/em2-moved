import traceback
from functools import update_wrapper

from aiohttp.web import Application, HTTPBadRequest, HTTPNotFound, Request  # noqa
from asyncpg.connection import Connection  # noqa
from pydantic import BaseModel, EmailStr


class Session(BaseModel):
    address: EmailStr = ...
    recipient_id: int = None


class View:
    def __init__(self, request):
        self.request: Request = request
        self.app: Application = request.app
        self.conn: Connection = request['conn']
        self.session: Session = request['session']

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

    async def fetchval404(self, sql, *args, msg=None):
        return await _fetch404(self.conn.fetchval, sql, *args, msg=msg)

    async def fetchrow404(self, sql, *args, msg=None):
        return await _fetch404(self.conn.fetchrow, sql, *args, msg=msg)

    async def request_json(self):
        try:
            data = await self.request.json()
        except ValueError as e:
            raise HTTPBadRequest(text=f'invalid request json: {e}')
        if not isinstance(data, dict):
            raise HTTPBadRequest(text='request json should be a dictionary')
        return data


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
