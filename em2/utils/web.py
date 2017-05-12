import json

from aiohttp.web import HTTPBadRequest, Response
from pydantic import BaseModel, ValidationError


JSON_CONTENT_TYPE = 'application/json'


def json_response(*, status_=200, list_=None, **data):
    return Response(
        body=json.dumps(data if list_ is None else list_).encode(),
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
