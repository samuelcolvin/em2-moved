from typing import List

from aiohttp.web_exceptions import HTTPBadRequest, HTTPNotFound
from pydantic import BaseModel, EmailStr, ValidationError, constr

from em2.core import Components, Verbs, hash_id
from em2.utils.web import json_response, raw_json_response


LIST_CONVS = """
SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
FROM (
  SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  LEFT OUTER JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1
  ORDER BY c.id DESC LIMIT 50
) t;
"""


async def vlist(request):
    raw_json = await request['conn'].fetchval(LIST_CONVS, request['session'].recipient_id)
    return raw_json_response(raw_json)


CONV_DETAILS = """
SELECT row_to_json(t)
FROM (
  SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1 AND c.hash = $2
) t;
"""


async def get(request):
    conv_hash = request.match_info['conv']
    details = await request['conn'].fetchval(CONV_DETAILS, request['session'].recipient_id, conv_hash)
    if details is None:
        raise HTTPNotFound(reason=f'conversation {conv_hash} not found')
    # TODO get the rest
    return raw_json_response(details)


class CreateConvModel(BaseModel):
    subject: constr(max_length=255) = ...
    message: str = ...
    participants: List[EmailStr] = []


GET_EXISTING_RECIPIENTS = 'SELECT id, address FROM recipients WHERE address = any($1)'
SET_MISSING_RECIPIENTS = """
INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
RETURNING id
"""
CREATE_CONV = """
INSERT INTO conversations (creator, subject)
VALUES ($1, $2) RETURNING id
"""
ADD_PARTICIPANT = 'INSERT INTO participants (conversation, recipient) VALUES ($1, $2)'
ADD_MESSAGE = 'INSERT INTO messages (hash, conversation, body) VALUES ($1, $2, $3)'


async def create_conv(request, conv: CreateConvModel):
    conn = request['conn']
    participant_addresses = set(conv.participants)
    participant_ids = set()
    if participant_addresses:
        for r in await conn.fetch(GET_EXISTING_RECIPIENTS, participant_addresses):
            participant_ids.add(r['id'])
            participant_addresses.remove(r['address'])

        if participant_addresses:
            extra_ids = {r['id'] for r in await conn.fetch(SET_MISSING_RECIPIENTS, participant_addresses)}
            participant_ids.update(extra_ids)

    conv_id = await conn.fetchval(CREATE_CONV, request['session'].recipient_id, conv.subject)
    if participant_ids:
        await conn.executemany(ADD_PARTICIPANT, {(conv_id, pid) for pid in participant_ids})
    message_hash = hash_id(request['session'].address, conv.message)
    await conn.execute(ADD_MESSAGE, message_hash, conv_id, conv.message)
    return conv_id


async def create(request):
    try:
        data = await request.json()
        conv = CreateConvModel(**data)
    except ValidationError as e:
        raise HTTPBadRequest(text=e.json())
    except (ValueError, TypeError):
        raise HTTPBadRequest(text='invalid request data')

    conn = request['conn']
    participant_addresses = set(conv.participants)
    participant_ids = set()
    if participant_addresses:
        for r in await conn.fetch(GET_EXISTING_RECIPIENTS, participant_addresses):
            participant_ids.add(r['id'])
            participant_addresses.remove(r['address'])

        if participant_addresses:
            extra_ids = {r['id'] for r in await conn.fetch(SET_MISSING_RECIPIENTS, participant_addresses)}
            participant_ids.update(extra_ids)

    conv_id = await conn.fetchval(CREATE_CONV, request['session'].recipient_id, conv.subject)
    if participant_ids:
        await conn.executemany(ADD_PARTICIPANT, {(conv_id, pid) for pid in participant_ids})
    message_hash = hash_id(request['session'].address, conv.message)
    await conn.execute(ADD_MESSAGE, message_hash, conv_id, conv.message)

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
