import json

from aiohttp.web_response import Response

JSON_CONTENT_TYPE = 'application/json'


def json_response(*, status_=200, list_=None, **data):
    return Response(
        body=json.dumps(data if list_ is None else list_).encode(),
        status=status_,
        content_type=JSON_CONTENT_TYPE,
    )


def raw_json_response(text, *, status_=200):
    return Response(
        text=text,
        status=status_,
        content_type=JSON_CONTENT_TYPE,
    )
