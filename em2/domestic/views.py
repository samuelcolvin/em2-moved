from aiohttp.web_exceptions import HTTPBadRequest, HTTPNotFound
from pydantic import ValidationError

from em2.core import CreateConvModel, conv_details, convs_json, create_conv
from em2.utils.web import json_response, raw_json_response


async def retrieve_list(request):
    return raw_json_response(await convs_json(request))


async def retrieve_conv(request):
    conv_id = request.match_info['conv']
    details = await conv_details(request, conv_id)
    if details is None:
        raise HTTPNotFound(reason=f'conversation {conv_id} not found')
    # TODO get the rest
    return raw_json_response(details)


async def new_conv(request):
    data = await request.json()
    try:
        conv = CreateConvModel(**data)
    except ValidationError as e:
        raise HTTPBadRequest(text=e.json())
    conv_id = await create_conv(request, conv)
    # url = request.app.router['draft-conv'].url_for(id=conv_id)
    return json_response(id=conv_id, status_=201)
