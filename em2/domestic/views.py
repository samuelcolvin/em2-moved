# from aiohttp.web_exceptions import HTTPNotFound
from aiohttp.web_response import Response

from em2.utils.encoding import JSON_CONTENT_TYPE


LIST_CONVS = """
SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
FROM (
  SELECT c.hash as hash, c.draft_hash as draft_hash, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  LEFT OUTER JOIN participants ON c.id = participants.conversation
  WHERE c.creator = $1 OR participants.recipient = $1
  ORDER BY c.id DESC LIMIT 50
) t;
"""


async def retrieve_list(request):
    r = await request['conn'].fetchval(LIST_CONVS, request['recipient_id'])
    return Response(text=r, content_type=JSON_CONTENT_TYPE)


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
