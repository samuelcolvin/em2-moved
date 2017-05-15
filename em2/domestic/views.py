from datetime import datetime
from typing import List

from aiohttp.web_exceptions import HTTPBadRequest
from pydantic import EmailStr, constr

from em2.core import Components, Verbs, gen_public_key, generate_conv_key
from em2.utils.web import WebModel, json_response, raw_json_response
from .common import View


class VList(View):
    sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT c.id AS id, c.key AS key, c.subject AS subject, c.timestamp AS ts, c.published AS published
      FROM conversations AS c
      LEFT JOIN participants ON c.id = participants.conversation
      WHERE participants.recipient = $1 AND participants.active = True
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
    WHERE p.recipient = $1 AND c.key = $2 AND p.active = True
    """
    conv_details_sql = """
    SELECT row_to_json(t)
    FROM (
      SELECT c.key AS key, c.subject AS subject, c.timestamp AS ts, r.address AS creator, c.published AS published
      FROM conversations AS c
      JOIN recipients AS r ON c.creator = r.id
      WHERE c.id = $1
    ) t;
    """

    messages_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT m1.key AS key, m2.key AS after, m1.child AS child, m1.active AS active, m1.body AS body
      FROM messages AS m1
      LEFT JOIN messages AS m2 ON m1.after = m2.id
      WHERE m1.conversation = $1 AND m1.active = True
    ) t;
    """

    participants_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT r.address AS address, p.readall AS readall
      FROM participants AS p
      JOIN recipients AS r ON p.recipient = r.id
      WHERE p.conversation = $1 AND p.active = True
    ) t;
    """

    actions_sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT a.key AS key, a.verb AS verb, a.component AS component, a.body AS body, a.timestamp AS timestamp,
      actor_recipient.address AS actor,
      a_parent.key AS parent,
      m.key AS message,
      prt_recipient.address AS participant
      FROM actions AS a

      LEFT JOIN actions AS a_parent ON a.parent = a_parent.id
      LEFT JOIN messages AS m ON a.message = m.id

      JOIN participants AS actor_prt ON a.actor = actor_prt.id
      JOIN recipients AS actor_recipient ON actor_prt.recipient = actor_recipient.id

      LEFT JOIN participants AS prt_prt ON a.participant = prt_prt.id
      LEFT JOIN recipients AS prt_recipient ON prt_prt.recipient = prt_recipient.id

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
    create_conv_sql = """
    INSERT INTO conversations (key, creator, subject)
    VALUES ($1, $2, $3) RETURNING id
    """
    add_participants_sql = 'INSERT INTO participants (conversation, recipient) VALUES ($1, $2)'
    add_message_sql = 'INSERT INTO messages (key, conversation, body) VALUES ($1, $2, $3)'

    class ConvModel(WebModel):
        subject: constr(max_length=255) = ...
        message: str = ...
        participants: List[EmailStr] = []

    async def call(self, request):
        conv = self.ConvModel(**await self.request_json())
        participant_addresses = set(conv.participants)
        participant_ids = set()
        if participant_addresses:
            for r in await self.conn.fetch(self.get_existing_recips_sql, participant_addresses):
                participant_ids.add(r['id'])
                participant_addresses.remove(r['address'])

            if participant_addresses:
                extra_ids = {r['id'] for r in await self.conn.fetch(self.set_missing_recips_sql, participant_addresses)}
                participant_ids.update(extra_ids)

        key = gen_public_key('draft')
        conv_id = await self.conn.fetchval(self.create_conv_sql, key, self.session.recipient_id, conv.subject)
        if participant_ids:
            await self.conn.executemany(self.add_participants_sql, {(conv_id, pid) for pid in participant_ids})
        await self.conn.execute(self.add_message_sql, gen_public_key('msg'), conv_id, conv.message)

        # url = request.app.router['draft-conv'].url_for(id=conv_id)
        return json_response(key=key, status_=201)


class Act(View):
    class Data(WebModel):
        conv: int = ...
        verb: Verbs = ...
        component: Components = ...
        actor: int = ...
        item: constr(max_length=255) = None
        parent: constr(min_length=20, max_length=20) = None
        body: str = None
        message_child: bool = False
        # TODO: participant permissions and more exotic types
        # TODO: add timezone event originally occurred in

        def validate_verb(self, v):
            if v is Verbs.PUBLISH:
                raise ValueError('use the publish endpoint, not "act" to publish conversations')
            return v

    get_conv_part_sql = """
    SELECT c.id, p.id
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conversation
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

        if data.component in (Components.MESSAGE, Components.PARTICIPANT) and not data.item:
            # TODO replace with method validation on Data
            raise HTTPBadRequest(text=f'item may not be null for {data.component} actions')

        async with self.conn.transaction():
            key, action_id = await self.apply_action(data)
        # TODO: fire propagate
        return json_response(key=key, status_=201)

    create_action_sql = """
    INSERT INTO actions (key, conversation, verb, component, actor, parent, participant, message, body)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    RETURNING id
    """

    async def apply_action(self, data: Data):
        message_id, participant_id, parent_id = None, None, None
        if data.component is Components.MESSAGE:
            if data.verb is Verbs.ADD:
                message_id = await self.add_message(data)
            else:
                message_id, parent_id = await self.mod_message(data)
        elif data.component is Components.PARTICIPANT:
            if data.verb is Verbs.ADD:
                participant_id = await self.add_participant(data)
            else:
                participant_id = await self.mod_participant(data)
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
        return key, action_id

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
    delete_recover_message_sql = 'UPDATE messages SET active = $1 WHERE id = $2'
    modify_message_sql = 'UPDATE messages SET body = $1 WHERE id = $2'

    async def mod_message(self, data: Data):
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
            await self.conn.execute(self.delete_recover_message_sql, data.verb == Verbs.RECOVER, message_id)
        elif data.verb == Verbs.MODIFY:
            if not data.body:
                raise HTTPBadRequest(text='body can not be empty when modifying a message')
            await self.conn.execute(self.modify_message_sql, data.body, message_id)
        # lock and unlock don't change the message
        return message_id, parent_id

    get_recipient_id = 'SELECT id FROM recipients WHERE address = $1'
    set_recipient_id = """
    INSERT INTO recipients (address) VALUES ($1)
    ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
    """
    add_participant_sql = """
    INSERT INTO participants (conversation, recipient) VALUES ($1, $2)
    ON CONFLICT DO NOTHING RETURNING id
    """

    async def add_participant(self, data: Data):
        try:
            address = EmailStr.validate(data.item)
        except (TypeError, ValueError):
            raise HTTPBadRequest(text='is not a valid email address')

        recipient_id = await self.conn.fetchval(self.get_recipient_id, address)
        if recipient_id is None:
            recipient_id = await self.conn.fetchval(self.set_recipient_id, address)
        part_id = await self.conn.fetchval(self.add_participant_sql, data.conv, recipient_id)
        if part_id is None:
            raise HTTPBadRequest(text='participant already exists on the conversation')
        return part_id

    find_participant_sql = """
    SELECT p.id FROM participants AS p
    JOIN recipients AS r ON p.recipient = r.id
    WHERE p.conversation = $1 AND r.address = $2
    """
    delete_participant_sql = 'UPDATE participants SET active = $1 WHERE id = $2'

    async def mod_participant(self, data: Data):
        # TODO check parent matches latest data.parent
        part_id = await self.fetchval404(self.find_participant_sql, data.conv, data.item)
        if data.verb in (Verbs.DELETE, Verbs.RECOVER):
            await self.conn.execute(self.delete_participant_sql, data.verb == Verbs.RECOVER, part_id)
        elif data.verb is Verbs.MODIFY:
            raise NotImplementedError()
        else:
            raise HTTPBadRequest(text=f'Invalid verb for participants, can only add, delete, recover or modify')
        return part_id


class Publish(View):
    get_conv_sql = """
    SELECT c.id, c.subject, p.id
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conversation
    WHERE c.published = False AND c.key = $1 AND c.creator = $2 AND p.recipient = $2
    """
    update_conv_sql = """
    UPDATE conversations SET key = $1, timestamp = $2, published = True
    WHERE id = $3
    """
    delete_actions_sql = 'DELETE FROM actions WHERE conversation = $1'
    create_action_sql = """
    INSERT INTO actions (key, conversation, actor, verb, component)
    VALUES ($1, $2, $3, 'publish', 'participant')
    RETURNING id
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id, subject, participant_id = await self.fetchrow404(
            self.get_conv_sql,
            conv_key,
            self.session.recipient_id
        )
        new_ts = datetime.utcnow()
        new_conv_key = generate_conv_key(self.session.address, new_ts, subject)
        async with self.conn.transaction():
            await self.conn.execute(
                self.update_conv_sql,
                new_conv_key,
                new_ts,
                conv_id,
            )
            # might need to not delete these actions, just mark them as draft somehow
            await self.conn.execute(self.delete_actions_sql, conv_id)
            action_id = await self.conn.fetchval(
                self.create_action_sql,
                gen_public_key('pub'),
                conv_id,
                participant_id,
            )
        print(action_id)
        # TODO: fire propagate
        return json_response(key=new_conv_key)
