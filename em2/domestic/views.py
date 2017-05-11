from aiohttp.web_exceptions import HTTPBadRequest, HTTPNotFound
from pydantic import BaseModel, ValidationError

from em2.core import Components, CreateConvModel, Verbs, conv_details, convs_json, create_conv
from em2.utils.web import json_response, raw_json_response


async def vlist(request):
    return raw_json_response(await convs_json(request))


async def get(request):
    conv_hash = request.match_info['conv']
    details = await conv_details(request, conv_hash)
    if details is None:
        raise HTTPNotFound(reason=f'conversation {conv_hash} not found')
    # TODO get the rest
    return raw_json_response(details)


async def create(request):
    try:
        data = await request.json()
        conv = CreateConvModel(**data)
    except ValidationError as e:
        raise HTTPBadRequest(text=e.json())
    except (ValueError, TypeError):
        raise HTTPBadRequest(text='invalid request data')
    conv_id = await create_conv(request, conv)
    # url = request.app.router['draft-conv'].url_for(id=conv_id)
    return json_response(id=conv_id, status_=201)


GET_CONV_PART = """
SELECT c.id as conv_id, p.id as participant
FROM conversations AS c
JOIN participants as p ON c.id = p.conversation
WHERE c.hash = $1 AND p.recipient = $2
"""


async def _conv_id_participant(request, conv_hash):
    return await request['conn'].fetchrow(GET_CONV_PART, conv_hash, request['session'].recipient_id)


class ActionModel(BaseModel):
    conversation: int = ...
    verb: Verbs = ...
    component: Components = ...
    actor: int = ...
    parent: int = None
    participant: int = None
    message: int = None
    body: str = None

    def validate_participant(self, v):
        if self.component is Components.PARTICIPANT and v is None:
            raise ValueError('participant can not be null if the component is participants')
        return v

    def validate_message(self, v):
        print('validate_message', v)
        if self.component is Components.MESSAGE and v is None:
            raise ValueError('message can not be null if the component is messages')
        return v


async def _apply_action(request, action: ActionModel):
    if action.component is Components.MESSAGE:
        pass
    elif action.component is Components.PARTICIPANT:
        pass
    else:
        raise NotImplementedError()


async def act(request):
    conv_hash = request.match_info['conv']
    try:
        conv_id, actor_id = await _conv_id_participant(request, conv_hash)
    except TypeError:
        # TypeError if conv_actor is None because query returned nothing
        raise HTTPNotFound(reason=f'conversation {conv_hash} not found')

    try:
        data = await request.json()
        action = ActionModel(
            conversation=conv_id,
            actor=actor_id,
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            **data
        )
    except ValidationError as e:
        raise HTTPBadRequest(text=e.json())
    except (ValueError, TypeError):
        raise HTTPBadRequest(text='invalid request data')

    await _apply_action(request, action)
    return json_response(id=None, status_=201)
