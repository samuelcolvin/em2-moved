import datetime
import json

from aiohttp.web_response import Response

from em2.utils import to_unix_ms

JSON_CONTENT_TYPE = 'application/json'


class UniversalEncoder(json.JSONEncoder):
    ENCODER_BY_TYPE = {
        # UUID: str,
        datetime.datetime: to_unix_ms,
        # datetime.date: to_unix_ms,
        # datetime.time: to_unix_ms,
        # set: list,
        # frozenset: list,
        # GeneratorType: list,
        # bytes: lambda o: o.decode(),
        # RowProxy: dict,
    }

    def default(self, obj):
        try:
            encoder = self.ENCODER_BY_TYPE[type(obj)]
        except KeyError:
            return super().default(obj)
        return encoder(obj)


def to_pretty_json(data):
    return json.dumps(data, indent=2, sort_keys=True, cls=UniversalEncoder) + '\n'


def json_response(request, *, status_=200, list_=None, **data):
    if JSON_CONTENT_TYPE in request.headers.get('Accept', ''):
        # could use ujson
        to_json = json.dumps
    else:
        to_json = to_pretty_json

    return Response(
        body=to_json(data if list_ is None else list_).encode(),
        status=status_,
        content_type=JSON_CONTENT_TYPE,
    )
