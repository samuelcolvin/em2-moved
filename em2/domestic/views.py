import logging
from datetime import datetime
from typing import List

from aiohttp import WSMsgType
from aiohttp.web_ws import WebSocketResponse
from pydantic import EmailStr, constr

from em2.core import ApplyAction, GetConv, gen_random, generate_conv_key
from em2.utils.web import WebModel, json_response, raw_json_response

from .common import View

logger = logging.getLogger('em2.domestic.views')


class VList(View):
    sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT c.id AS id, c.key AS key, c.subject AS subject, c.timestamp AS ts, c.published AS published
      FROM conversations AS c
      LEFT JOIN participants ON c.id = participants.conv
      WHERE participants.recipient = $1 AND participants.active = True
      ORDER BY c.id DESC LIMIT 50
    ) t;
    """

    async def call(self, request):
        raw_json = await self.conn.fetchval(self.sql, request['session'].recipient_id)
        return raw_json_response(raw_json)


class Get(View):
    async def call(self, request):
        conv_key = request.match_info['conv']
        json_str = await GetConv(self.conn).run(conv_key, self.session.address)
        return raw_json_response(json_str)


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
    add_participants_sql = 'INSERT INTO participants (conv, recipient) VALUES ($1, $2)'
    add_message_sql = 'INSERT INTO messages (key, conv, body) VALUES ($1, $2, $3)'

    class ConvModel(WebModel):
        subject: constr(max_length=255) = ...
        message: str = ...
        participants: List[EmailStr] = []

    async def call(self, request):
        conv = self.ConvModel(**await self.request_json())
        part_addresses = set(conv.participants)
        part_ids = set()
        if part_addresses:
            for r in await self.conn.fetch(self.get_existing_recips_sql, part_addresses):
                part_ids.add(r['id'])
                part_addresses.remove(r['address'])

            if part_addresses:
                extra_ids = {r['id'] for r in await self.conn.fetch(self.set_missing_recips_sql, part_addresses)}
                part_ids.update(extra_ids)

        key = gen_random('draft')
        conv_id = await self.conn.fetchval(self.create_conv_sql, key, self.session.recipient_id, conv.subject)
        if part_ids:
            await self.conn.executemany(self.add_participants_sql, {(conv_id, pid) for pid in part_ids})
        await self.conn.execute(self.add_message_sql, gen_random('msg'), conv_id, conv.message)

        return json_response(url=str(request.app.router['get'].url_for(conv=key)), status_=201)


class Act(View):
    get_conv_part_sql = """
    SELECT c.id, c.published, p.id
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    WHERE c.key = $1 AND p.recipient = $2
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id, conv_published, actor_id = await self.fetchrow404(
            self.get_conv_part_sql,
            conv_key,
            self.session.recipient_id,
            msg=f'conversation {conv_key} not found'
        )

        apply_action = ApplyAction(
            self.conn,
            remote_action=False,
            action_key=gen_random('act'),
            conv=conv_id,
            actor=actor_id,
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            **await self.request_json()
        )
        await apply_action.run()

        if conv_published:
            await self.pusher.push(apply_action.action_id)
        return json_response(
            key=apply_action.data.action_key,
            conv_key=conv_key,
            component=apply_action.data.component,
            verb=apply_action.data.verb,
            timestamp=apply_action.action_timestamp,
            parent=apply_action.data.parent,
            relationship=apply_action.data.relationship,
            body=apply_action.data.body,
            item=apply_action.item_key,
            status_=201,
        )


class Publish(View):
    get_conv_sql = """
    SELECT c.id, c.subject, p.id
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    WHERE c.published = False AND c.key = $1 AND c.creator = $2 AND p.recipient = $2
    """
    update_conv_sql = """
    UPDATE conversations SET key = $1, timestamp = $2, published = True
    WHERE id = $3
    """
    delete_actions_sql = 'DELETE FROM actions WHERE conv = $1'
    create_action_sql = """
    INSERT INTO actions (key, conv, actor, verb, component)
    VALUES ($1, $2, $3, 'add', 'participant')
    RETURNING id, timestamp
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id, subject, part_id = await self.fetchrow404(
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
            action_key = gen_random('pub')
            action_id, action_timestamp = await self.conn.fetchrow(
                self.create_action_sql,
                action_key,
                conv_id,
                part_id,
            )

        await self.pusher.push(action_id)
        return json_response(key=new_conv_key)


class Websocket(View):
    ws_type_lookup = {k.value: v for v, k in WSMsgType.__members__.items()}

    async def call(self, request):
        ws = WebSocketResponse()
        await ws.prepare(request)
        logger.info('ws connection from %d', self.session)
        await self.app['background'].add_recipient(self.session.recipient_id, ws)
        try:
            async for msg in ws:
                if msg.tp == WSMsgType.TEXT:
                    logger.info('ws message: %s', msg.data)
                elif msg.tp == WSMsgType.ERROR:
                    pass
                    logger.warning('ws connection closed with exception %s', ws.exception())
                else:
                    pass
                    logger.warning('unknown websocket message type %s, data: %s', self.ws_type_lookup[msg.tp], msg.data)
        finally:
            logger.debug('ws disconnection: %d', self.session)
            await self.app['background'].remove_recipient(self.session.recipient_id)
        return ws
