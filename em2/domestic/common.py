from pydantic import BaseModel, EmailStr

from em2.utils.web import ViewMain


class Session(BaseModel):
    address: EmailStr = ...
    recipient_id: int = None


class View(ViewMain):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']
