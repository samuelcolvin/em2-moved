from typing import List

from aiohttp.web_exceptions import HTTPBadRequest
from pydantic import EmailStr, constr

from em2.core import Components, Verbs, gen_message_key
from em2.utils.web import WebModel, json_response, raw_json_response
from .common import View


class VList(View):
    sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
      FROM conversations AS c
      LEFT OUTER JOIN participants ON c.id = participants.conversation
      WHERE participants.recipient = $1
      ORDER BY c.id DESC LIMIT 50
    ) t;
    """

    async def call(self, request):
        raw_json = await self.conn.fetchval(self.sql, request['session'].recipient_id)
        return raw_json_response(raw_json)


class Get(View):
    conv_details = """
    SELECT row_to_json(t)
    FROM (
      SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
      FROM conversations AS c
      JOIN participants ON c.id = participants.conversation
      WHERE participants.recipient = $1 AND c.hash = $2
    ) t;
    """

    async def call(self, request):
        conv_hash = request.match_info['conv']
        details = await self.fetchval404(
            self.conv_details,
            self.session.recipient_id,
            conv_hash,
            text=f'conversation {conv_hash} not found'
        )
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

    class ConvModel(WebModel):
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
        conv = self.ConvModel(**await self.request_json())
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
    find_message = """
    SELECT m.id FROM messages AS m
    WHERE m.conversation = $1 AND m.key = $2
    """
    add_message_sql = """
    INSERT INTO messages (key, conversation, follows, child, body) VALUES ($1, $2, $3, $4, $5)
    RETURNING id
    """
    latest_message_action = """
    SELECT id, verb, actor FROM actions
    WHERE conversation = $1 AND message = $2
    ORDER BY id DESC
    LIMIT 1
    """

    class Data(WebModel):
        conv: int = ...
        verb: Verbs = ...
        component: Components = ...
        actor: int = ...
        item: str = None
        parent: constr(min_length=40, max_length=40) = None
        body: str = None
        message_child: bool = False
        # TODO: participant permissions and more exotic types

    """
    Actions parents:
    * can always add a new message or participant, parent doesn't matter
    * if editing, deleting, locking, unlocking a message, parent must be the last event on that message.
    * subject, expiry etc. parent be the most recent on that meta property.
    """

    async def add_message(self, data: Data):
        follows_id = await self.fetchval404(self.find_message, data.conv, data.item)
        args = gen_message_key(), data.conv, follows_id, data.message_child, data.body
        message_id = await self.conn.fetchval(self.add_message_sql, *args)
        return message_id

    async def modify_message(self, data: Data):
        message_id = await self.fetchval404(self.find_message, data.conv, data.item)

        return message_id

    async def _apply_action(self, action: Data):
        # TODO: in transaction
        if action.component is Components.MESSAGE:
            if not action.item:
                # TODO replace with method validation on Data
                raise HTTPBadRequest(text='item may not be null for message actions')
            if action.verb is Verbs.ADD:
                message_id = self.add_message(action)
            else:
                message_id = self.modify_message(action)
            await self.modify_message(action)
        elif action.component is Components.PARTICIPANT:
            pass
        else:
            raise NotImplementedError()
        return message_id

    async def call(self, request):
        conv_hash = request.match_info['conv']
        conv_id, actor_id = await self.fetchrow404(
            self.get_conv_part,
            conv_hash,
            self.session.recipient_id,
            text=f'conversation {conv_hash} not found'
        )

        data = self.Data(
            conv=conv_id,
            actor=actor_id,
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            **await self.request_json()
        )

        await self._apply_action(data)
        return json_response(id=None, status_=201)
