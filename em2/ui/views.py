from em2.core import Retrieval, RVerbs
from .utils import json_response


async def retrieve_list(request):
    retrieval = Retrieval(request['address'], verb=RVerbs.LIST)
    conversations = await request.app['main']['controller'].retrieve(retrieval)
    return json_response(request, list_=conversations)
