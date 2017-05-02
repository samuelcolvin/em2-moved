from aiohttp.web_exceptions import HTTPNotFound

from em2.core import Retrieval, RVerbs
from em2.exceptions import ConversationNotFound
from .utils import json_response


async def retrieve_list(request):
    retrieval = Retrieval(request['address'], verb=RVerbs.LIST)
    conversations = await request.app['controller'].retrieve(retrieval)
    return json_response(request, list_=conversations)


async def retrieve_conv(request):
    conv_id = request.match_info['conv']
    retrieval = Retrieval(request['address'], conversation=conv_id)
    try:
        conversation = await request.app['controller'].retrieve(retrieval)
    except ConversationNotFound as e:
        raise HTTPNotFound(reason=e)
    return json_response(
        request,
        **conversation,
    )
