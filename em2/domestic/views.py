from typing import List

from aiohttp.web_exceptions import HTTPBadRequest
from pydantic import EmailStr, constr

from em2.core import Components, Verbs, gen_public_key
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
            msg=f'conversation {conv_hash} not found'
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
        await self.conn.execute(self.add_message, gen_public_key(), conv_id, conv.message)
        return conv_id

    async def call(self, request):
        conv = self.ConvModel(**await self.request_json())
        # url = request.app.router['draft-conv'].url_for(id=conv_id)
        conv_id = await self.get_conv_id(conv)
        return json_response(id=conv_id, status_=201)


class Act(View):
    class Data(WebModel):
        conv: int = ...
        verb: Verbs = ...
        component: Components = ...
        actor: int = ...
        item: str = None
        parent: constr(min_length=20, max_length=20) = None
        body: str = None
        message_child: bool = False
        # TODO: participant permissions and more exotic types

    get_conv_part = """
    SELECT c.id as conv_id, p.id as participant
    FROM conversations AS c
    JOIN participants as p ON c.id = p.conversation
    WHERE c.hash = $1 AND p.recipient = $2
    """

    async def call(self, request):
        conv_hash = request.match_info['conv']
        conv_id, actor_id = await self.fetchrow404(
            self.get_conv_part,
            conv_hash,
            self.session.recipient_id,
            msg=f'conversation {conv_hash} not found'
        )

        data = self.Data(
            conv=conv_id,
            actor=actor_id,
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            **await self.request_json()
        )

        key = await self.apply_action(data)
        return json_response(key=key, status_=201)

    create_action = """
    INSERT INTO actions (key, conversation, verb, component, actor, parent, participant, message, body)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    RETURNING id
    """

    async def apply_action(self, data: Data):
        # TODO: in transaction
        message_id, participant_id, parent_id = None, None, None
        if data.component is Components.MESSAGE:
            if not data.item:
                # TODO replace with method validation on Data
                raise HTTPBadRequest(text='item may not be null for message actions')

            if data.verb is Verbs.ADD:
                message_id = await self.add_message(data)
            else:
                message_id, parent_id = await self.modify_message(data)
        elif data.component is Components.PARTICIPANT:
            raise NotImplementedError()
        else:
            raise NotImplementedError()

        key = gen_public_key()
        action_id = await self.conn.fetchval(
            self.create_action,
            key,
            data.conv,
            data.verb,
            data.component,
            data.actor,
            parent_id,
            participant_id,
            message_id,
            data.body,
        )
        print(action_id)
        return key

    find_message = """
    SELECT m.id FROM messages AS m
    WHERE m.conversation = $1 AND m.key = $2
    """
    add_message_sql = """
    INSERT INTO messages (key, conversation, follows, child, body) VALUES ($1, $2, $3, $4, $5)
    RETURNING id
    """

    async def add_message(self, data: Data):
        follows_id = await self.fetchval404(self.find_message, data.conv, data.item)
        args = gen_public_key(), data.conv, follows_id, data.message_child, data.body
        message_id = await self.conn.fetchval(self.add_message_sql, *args)
        return message_id

    latest_message_action = """
    SELECT id, key, verb, actor FROM actions
    WHERE conversation = $1 AND message = $2
    ORDER BY id DESC
    LIMIT 1
    """

    delete_recover_message = """
    UPDATE messages SET deleted = $1
    WHERE id = $2
    """

    modify_message_sql = """
    UPDATE messages SET body = $1
    WHERE id = $2
    """

    async def modify_message(self, data: Data):
        message_id = await self.fetchval404(self.find_message, data.conv, data.item)
        parent_id, parent_key, parent_verb, parent_actor = await self.fetchrow404(
            self.latest_message_action,
            data.conv,
            message_id
        )
        if data.parent != parent_key:
            raise HTTPBadRequest(text=f'parent does not match latest action on the message: {parent_key}')

        if parent_actor != data.actor and parent_verb == Verbs.LOCK:
            raise HTTPBadRequest(text=f'message {data.item} is locked and cannot be updated')
        # could do more validation here to enforce:
        # * locking before modification
        # * not modifying deleted messages
        # * not repeatedly recovering messages
        if data.verb in (Verbs.DELETE, Verbs.RECOVER):
            await self.conn.execute(self.delete_recover_message, data.verb == Verbs.DELETE, message_id)
        elif data.verb == Verbs.MODIFY:
            if not data.body:
                raise HTTPBadRequest(text='body can not be empty when modifying a message')
            await self.conn.execute(self.modify_message_sql, data.body, message_id)
        # lock and unlock don't change the message
        return message_id, parent_id
