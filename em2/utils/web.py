import datetime
import json

from aiohttp.web import HTTPBadRequest, Response
from pydantic import BaseModel, ValidationError

JSON_CONTENT_TYPE = 'application/json'


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
