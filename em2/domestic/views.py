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
      SELECT c.id as id, c.key as key, c.subject as subject, c.timestamp as ts
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
    get_conv_id_sql = """
    SELECT c.id FROM conversations AS c
    JOIN participants AS p ON c.id = p.conversation
    WHERE p.recipient = $1 AND c.key = $2
    """
    conv_details_sql = """
    SELECT row_to_json(t)
    FROM (
      SELECT c.key as key, c.subject as subject, c.timestamp as ts, r.address as creator
      FROM conversations AS c
      JOIN recipients AS r ON c.creator = r.id
      WHERE c.id = $1
    ) t;
    """

    messages_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT key, after, child, deleted, body FROM messages
      WHERE conversation = $1
    ) t;
    """

    participants_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT r.address as address, p.readall as readall
      FROM participants as p
      JOIN recipients AS r ON p.recipient = r.id
      WHERE p.conversation = $1 AND p.deleted = False
    ) t;
    """

    actions_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT a.key as key, a.verb AS verb, a.component AS component, a.body AS body, a.timestamp AS timestamp,
      actor_recipient.address AS actor,
      a_parent.key AS parent,
      m.key AS message,
      prt_recipient.address AS participant
      FROM actions AS a

      LEFT OUTER JOIN actions AS a_parent ON a.parent = a_parent.id
      LEFT OUTER JOIN messages AS m ON a.message = m.id

      JOIN participants AS actor_prt ON a.actor = actor_prt.id
      JOIN recipients AS actor_recipient ON actor_prt.recipient = actor_recipient.id

      LEFT OUTER JOIN participants AS prt_prt ON a.participant = prt_prt.id
      LEFT OUTER JOIN recipients AS prt_recipient ON prt_prt.recipient = prt_recipient.id

      WHERE a.conversation = $1
    ) t;
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id = await self.fetchval404(
            self.get_conv_id_sql,
            self.session.recipient_id,
            conv_key,
            msg=f'conversation {conv_key} not found'
        )
        details = await self.conn.fetchval(self.conv_details_sql, conv_id)
        messages = await self.conn.fetchval(self.messages_sql, conv_id)
        participants = await self.conn.fetchval(self.participants_sql, conv_id)
        actions = await self.conn.fetchval(self.actions_sql, conv_id)
        return raw_json_response(
            '{'
            f'"details":{details},'
            f'"messages":{messages},'
            f'"participants":{participants or "null"},'
            f'"actions":{actions or "null"}'
            '}'
        )


class Create(View):
    get_existing_recips_sql = 'SELECT id, address FROM recipients WHERE address = any($1)'
    set_missing_recips_sql = """
    INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
    ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
    RETURNING id
    """
    create_sql = """
    INSERT INTO conversations (creator, subject)
    VALUES ($1, $2) RETURNING id
    """
    add_participants_sql = 'INSERT INTO participants (conversation, recipient) VALUES ($1, $2)'
    add_message_sql = 'INSERT INTO messages (key, conversation, body) VALUES ($1, $2, $3)'

    class ConvModel(WebModel):
        subject: constr(max_length=255) = ...
        message: str = ...
        participants: List[EmailStr] = []

    async def get_conv_id(self, conv):
        participant_addresses = set(conv.participants)
        participant_ids = set()
        if participant_addresses:
            for r in await self.conn.fetch(self.get_existing_recips_sql, participant_addresses):
                participant_ids.add(r['id'])
                participant_addresses.remove(r['address'])

            if participant_addresses:
                extra_ids = {r['id'] for r in await self.conn.fetch(self.set_missing_recips_sql, participant_addresses)}
                participant_ids.update(extra_ids)

        conv_id = await self.conn.fetchval(self.create_sql, self.session.recipient_id, conv.subject)
        if participant_ids:
            await self.conn.executemany(self.add_participants_sql, {(conv_id, pid) for pid in participant_ids})
        await self.conn.execute(self.add_message_sql, gen_public_key('msg'), conv_id, conv.message)
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
        # TODO: add timezone event originally occurred in

    get_conv_part_sql = """
    SELECT c.id as conv_id, p.id as participant
    FROM conversations AS c
    JOIN participants as p ON c.id = p.conversation
    WHERE c.key = $1 AND p.recipient = $2
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id, actor_id = await self.fetchrow404(
            self.get_conv_part_sql,
            conv_key,
            self.session.recipient_id,
            msg=f'conversation {conv_key} not found'
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

    create_action_sql = """
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

        key = gen_public_key('act')
        action_id = await self.conn.fetchval(
            self.create_action_sql,
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
        # TODO: fire job
        print(action_id)
        return key

    find_message_sql = """
    SELECT m.id FROM messages AS m
    WHERE m.conversation = $1 AND m.key = $2
    """
    add_message_sql = """
    INSERT INTO messages (key, conversation, after, child, body) VALUES ($1, $2, $3, $4, $5)
    RETURNING id
    """

    async def add_message(self, data: Data):
        after_id = await self.fetchval404(self.find_message_sql, data.conv, data.item)
        if not data.body:
            raise HTTPBadRequest(text='body can not be empty when adding a message')
        args = gen_public_key('msg'), data.conv, after_id, data.message_child, data.body
        message_id = await self.conn.fetchval(self.add_message_sql, *args)
        return message_id

    latest_message_action_sql = """
    SELECT id, key, verb, actor FROM actions
    WHERE conversation = $1 AND message = $2
    ORDER BY id DESC
    LIMIT 1
    """

    delete_recover_message_sql = """
    UPDATE messages SET deleted = $1
    WHERE id = $2
    """

    modify_message_sql = """
    UPDATE messages SET body = $1
    WHERE id = $2
    """

    async def modify_message(self, data: Data):
        message_id = await self.fetchval404(self.find_message_sql, data.conv, data.item)
        parent_id, parent_key, parent_verb, parent_actor = await self.fetchrow404(
            self.latest_message_action_sql,
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
            await self.conn.execute(self.delete_recover_message_sql, data.verb == Verbs.DELETE, message_id)
        elif data.verb == Verbs.MODIFY:
            if not data.body:
                raise HTTPBadRequest(text='body can not be empty when modifying a message')
            await self.conn.execute(self.modify_message_sql, data.body, message_id)
        # lock and unlock don't change the message
        return message_id, parent_id
