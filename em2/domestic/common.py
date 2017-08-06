from aiohttp.web import HTTPBadRequest
from pydantic import BaseModel, EmailStr

from em2.utils.web import View as _View


class Session(BaseModel):
    address: EmailStr = ...
    recipient_id: int = None


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']

    async def request_json(self):
        try:
            data = await self.request.json()
        except ValueError as e:
            raise HTTPBadRequest(text=f'invalid request json: {e}')
        if not isinstance(data, dict):
            raise HTTPBadRequest(text='request json should be a dictionary')
        return data
