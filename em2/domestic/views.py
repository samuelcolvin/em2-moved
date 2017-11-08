import logging
from datetime import datetime
from typing import List, NamedTuple

from aiohttp import WSMsgType
from aiohttp.web import WebSocketResponse
from asyncpg import UniqueViolationError
from cryptography.fernet import InvalidToken
from pydantic import EmailStr, constr, validator

from em2.core import ApplyAction, GetConv, create_missing_recipients, gen_random, generate_conv_key
from em2.utils.web import JsonError, ViewMain, WebModel, json_response, raw_json_response

logger = logging.getLogger('em2.d.views')


class Session(NamedTuple):
    recipient_id: int
    address: str


class View(ViewMain):
    def __init__(self, request):
        super().__init__(request)
        self.session = Session(*request['session_args'])


class VList(View):
    sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT c.key AS key, c.subject AS subject, c.timestamp AS ts, c.published AS published
      FROM conversations AS c
      LEFT JOIN participants ON c.id = participants.conv
      WHERE participants.recipient = $1
      ORDER BY c.timestamp, c.id DESC LIMIT 50
    ) t;
    """

    async def call(self, request):
        raw_json = await self.conn.fetchval(self.sql, self.session.recipient_id)
        return raw_json_response(raw_json or '[]')


class Get(View):
    async def call(self, request):
        conv_key = request.match_info['conv']
        inc_states = bool(request.query.get('states'))
        json_str = await GetConv(self.conn).run(conv_key, self.session.address, inc_states=inc_states)
        return raw_json_response(json_str)


class Create(View):
    create_conv_sql = """
    INSERT INTO conversations (key, creator, subject)
    VALUES ($1, $2, $3) RETURNING id
    """
    add_participants_sql = 'INSERT INTO participants (conv, recipient) VALUES ($1, $2)'
    add_message_sql = 'INSERT INTO messages (conv, key, body) VALUES ($1, $2, $3)'

    class ConvModel(WebModel):
        subject: constr(max_length=255) = ...
        message: str = ...
        participants: List[EmailStr] = []
        conv_key: str = None
        msg_key: str = None

        @validator('conv_key', 'msg_key', always=True, pre=True)
        def set_default_key(cls, v, field, **kw):
            prefix = 'dft' if field.name == 'conv_key' else 'msg'
            return v or gen_random(prefix)

        @validator('conv_key', 'msg_key')
        def validate_keys(cls, v, field, **kw):
            prefix = 'dft' if field.name == 'conv_key' else 'msg'
            if not v.startswith(prefix + '-') or len(v) != 20:
                raise ValueError('invalid key')
            if v != v.lower():
                raise ValueError('key must be lower case')
            return v

    async def call(self, request):
        conv = self.ConvModel(**await self.request_json())
        participants = set(conv.participants)
        participants.add(self.session.address)
        recip_ids = await create_missing_recipients(self.conn, participants)
        recip_ids = set(recip_ids.values())

        async with self.conn.transaction():
            try:
                conv_id = await self.conn.fetchval(self.create_conv_sql,
                                                   conv.conv_key, self.session.recipient_id, conv.subject)
            except UniqueViolationError:
                raise JsonError.HTTPConflict(error='key conflicts with existing conversation')
            await self.conn.executemany(self.add_participants_sql, {(conv_id, rid) for rid in recip_ids})
            await self.conn.execute(self.add_message_sql, conv_id, conv.msg_key, conv.message)
        return json_response(key=conv.conv_key, status_=201)


class Act(View):
    get_conv_part_sql = """
    SELECT c.id, c.published
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    WHERE c.key LIKE $1 AND p.recipient = $2
    ORDER BY c.timestamp, c.id DESC
    LIMIT 1
    """

    async def call(self, request):
        conv_key = request.match_info['conv']
        conv_id, conv_published = await self.fetchrow404(
            self.get_conv_part_sql,
            conv_key + '%',
            self.session.recipient_id,
            msg=f'conversation {conv_key} not found'
        )

        apply_action = ApplyAction(
            self.conn,
            remote_action=False,
            action_key=gen_random('act'),
            conv=conv_id,
            published=conv_published,
            actor=self.session.recipient_id,
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            **await self.request_json()
        )
        await apply_action.run()

        await self.pusher.push(apply_action.action_id, actor_only=not conv_published)
        return json_response(
            key=apply_action.data.action_key,
            conv_key=conv_key,
            component=apply_action.data.component,
            verb=apply_action.data.verb,
            ts=apply_action.action_timestamp,
            parent=apply_action.data.parent,
            relationship=apply_action.data.relationship,
            body=apply_action.data.body,
            item=apply_action.item_key,
        )


class Publish(View):
    get_conv_sql = """
    SELECT c.id, c.subject
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    WHERE c.published = False AND c.key LIKE $1 AND c.creator = $2 AND p.recipient = $2
    ORDER BY c.timestamp, c.id DESC
    LIMIT 1
    """
    update_conv_sql = """
    UPDATE conversations SET key = $1, timestamp = $2, published = True
    WHERE id = $3
    """
    delete_actions_sql = 'DELETE FROM actions WHERE conv = $1'
    create_action_sql = """
    INSERT INTO actions (key, conv, actor, verb, message)
    SELECT $1, $2, $3, 'publish', m.id
    FROM messages as m
    WHERE m.conv = $2
    LIMIT 1
    RETURNING id, timestamp
    """

    async def call(self, request):
        old_conv_key = request.match_info['conv']
        conv_id, subject = await self.fetchrow404(
            self.get_conv_sql,
            old_conv_key + '%',
            self.session.recipient_id
        )
        new_ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.address, new_ts, subject)
        async with self.conn.transaction():
            await self.conn.execute(
                self.update_conv_sql,
                conv_key,
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
                self.session.recipient_id,
            )
        logger.info('published %s, old key %s', conv_key, old_conv_key)
        await self.pusher.push(action_id)
        return json_response(key=conv_key)


class Websocket(ViewMain):
    async def call(self, request):
        ws = WebSocketResponse()

        cookie = request.cookies.get(request.app['settings'].cookie_name, '')
        try:
            token = request.app['session_fernet'].decrypt(cookie.encode())
        except InvalidToken:
            await ws.prepare(request)
            await ws.close(code=4403)
        else:
            await request.app['activate_session'](request, token.decode())
            session = Session(*request['session_args'])
            logger.info('ws connection %s', session)
            await ws.prepare(request)
            await self.app['background'].add_recipient(session.recipient_id, ws)
            try:
                async for msg in ws:
                    # TODO process messages
                    if msg.tp == WSMsgType.TEXT:
                        logger.info('ws message from %s: %s', session, msg.data)
                    elif msg.tp == WSMsgType.ERROR:
                        pass
                        logger.warning('ws connection closed with exception %s', ws.exception())
                    else:
                        pass
                        logger.warning('unknown websocket message type %r, data: %s', msg.tp, msg.data)
            finally:
                logger.info('ws disconnection %s', session)
                await self.app['background'].remove_recipient(session.recipient_id)
        return ws
