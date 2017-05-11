from aiohttp.web_exceptions import HTTPNotFound
from aiohttp.web_response import Response

from em2.db import conversation_details, conversations_json
from em2.utils.encoding import JSON_CONTENT_TYPE


async def retrieve_list(request):
    return Response(text=await conversations_json(request), content_type=JSON_CONTENT_TYPE)


async def retrieve_conv(request):
    conv_id = request.match_info['conv']
    details = await conversation_details(request, conv_id)
    if details is None:
        raise HTTPNotFound(reason=f'conversation {conv_id} not found')
    # TODO get the rest
    return Response(text=details, content_type=JSON_CONTENT_TYPE)
