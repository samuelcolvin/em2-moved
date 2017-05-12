from typing import List

from aiohttp.web_exceptions import HTTPBadRequest, HTTPNotFound
from pydantic import BaseModel, EmailStr, ValidationError, constr

from em2.core import Components, Verbs, gen_message_key
from em2.utils.web import json_response, raw_json_response
from .common import View


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


class Create(View):
    get_existing_recips = 'SELECT id, address FROM recipients WHERE address = any($1)'
    set_missing_recips = """
    INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
    ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
    RETURNING id
    """
    create = """
    INSERT INTO conversations (creator, subject)
    VALUES ($1, $2) RETURNING id
    """
    add_participants = 'INSERT INTO participants (conversation, recipient) VALUES ($1, $2)'
    add_message = 'INSERT INTO messages (key, conversation, body) VALUES ($1, $2, $3)'

    class ConvModel(BaseModel):
        subject: constr(max_length=255) = ...
        message: str = ...
        participants: List[EmailStr] = []

    async def get_conv_id(self, conv):
        participant_addresses = set(conv.participants)
        participant_ids = set()
        if participant_addresses:
            for r in await self.conn.fetch(self.get_existing_recips, participant_addresses):
                participant_ids.add(r['id'])
                participant_addresses.remove(r['address'])

            if participant_addresses:
                extra_ids = {r['id'] for r in await self.conn.fetch(self.set_missing_recips, participant_addresses)}
                participant_ids.update(extra_ids)

        conv_id = await self.conn.fetchval(self.create, self.session.recipient_id, conv.subject)
        if participant_ids:
            await self.conn.executemany(self.add_participants, {(conv_id, pid) for pid in participant_ids})
        await self.conn.execute(self.add_message, gen_message_key(), conv_id, conv.message)
        return conv_id

    async def call(self, request):
        try:
            data = await request.json()
            conv = self.ConvModel(**data)
        except ValidationError as e:
            raise HTTPBadRequest(text=e.json())
        except (ValueError, TypeError):
            raise HTTPBadRequest(text='invalid request data')
        # url = request.app.router['draft-conv'].url_for(id=conv_id)
        conv_id = await self.get_conv_id(conv)
        return json_response(id=conv_id, status_=201)


class Act(View):
    get_conv_part = """
    SELECT c.id as conv_id, p.id as participant
    FROM conversations AS c
    JOIN participants as p ON c.id = p.conversation
    WHERE c.hash = $1 AND p.recipient = $2
    """
    message_follows = """
    SELECT m.id FROM messages AS m
    WHERE m.conversation = $1 AND m.key = $2
    """
    add_message = """
    INSERT INTO messages (key, conversation, follows, child, body) VALUES ($1, $2, $3, $4, $5)
    RETURNING id
    """

    class Action(BaseModel):
        conv: int = ...
        verb: Verbs = ...
        component: Components = ...
        actor: int = ...
        item: str = None
        parent: constr(min_length=16, max_length=16) = None
        body: str = None
        message_follows: constr(min_length=16, max_length=16) = None
        message_child: bool = False
        # TODO: participant permissions and more exotic types

    """
    Actions parents:
    * can always add a new message or participant, parent doesn't matter
    * if editing, deleting, locking, unlocking a message, parent must be the last event on that message.
    * subject, expiry etc. parent be the most recent on that meta property.
    """

    async def modify_message(self, action: Action):
        if action.verb is Verbs.ADD:
            if not action.message_follows:
                # TODO replace with method validation on Action
                raise HTTPBadRequest(text='message_follows may not be null when adding a message')

            follows_id = await self.conn.fetchval(self.message_follows, action.conv, action.message_follows)
            if not follows_id:
                raise HTTPBadRequest(text='message follower not found on conversation')
            args = gen_message_key(), action.conv, follows_id, action.message_child, action.body
            message_id = await self.conn.fetchval(self.add_message, *args)
            return message_id  # is this required?
        raise NotImplementedError()

    async def _apply_action(self, action: Action):
        # TODO in transaction
        if action.component is Components.MESSAGE:
            await self.modify_message(action)
        elif action.component is Components.PARTICIPANT:
            pass
        else:
            raise NotImplementedError()

    async def call(self, request):
        conn = request['conn']
        conv_hash = request.match_info['conv']
        try:
            conv_id, actor_id = await conn.fetchrow(self.get_conv_part, conv_hash, request['session'].recipient_id)
        except TypeError:
            # TypeError if conv_actor is None because query returned nothing
            raise HTTPNotFound(reason=f'conversation {conv_hash} not found')

        try:
            data = await request.json()
            action = self.Action(
                conv=conv_id,
                actor=actor_id,
                component=request.match_info['component'],
                verb=request.match_info['verb'],
                **data
            )
        except ValidationError as e:
            raise HTTPBadRequest(text=e.json())
        except (ValueError, TypeError):
            raise HTTPBadRequest(text='invalid request data')

        await self._apply_action(action)
        return json_response(id=None, status_=201)
