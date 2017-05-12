from functools import update_wrapper

from aiohttp.web import Application, Request  # noqa
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
