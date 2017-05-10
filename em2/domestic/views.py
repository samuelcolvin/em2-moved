# from aiohttp.web_exceptions import HTTPNotFound
from aiohttp.web_response import Response

from em2.db import conversations_json
from em2.utils.encoding import JSON_CONTENT_TYPE


async def retrieve_list(request):
    return Response(text=await conversations_json(request), content_type=JSON_CONTENT_TYPE)


async def retrieve_conv(request):
    return Response(text='', content_type=JSON_CONTENT_TYPE)
    # conv_id = request.match_info['conv']
    # retrieval = Retrieval(request['address'], conversation=conv_id)
    # try:
    #     conversation = await request.app['controller'].retrieve(retrieval)
    # except ConversationNotFound as e:
    #     raise HTTPNotFound(reason=e)
    # return json_response(
    #     request,
    #     **conversation,
    # )
