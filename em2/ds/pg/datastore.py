import logging
from aiopg.sa.engine import _create_engine
from sqlalchemy import column, join, select

from em2.core import Components, ConversationDataStore, DataStore
from em2.exceptions import ComponentNotFound, ConversationNotFound, Em2Exception, EventNotFound

from .models import sa_conversations, sa_events, sa_messages, sa_participants
from .utils import get_dsn

logger = logging.getLogger('em2.ds.pg')


sa_component_lookup = {
    Components.CONVERSATIONS: sa_conversations,
    Components.PARTICIPANTS: sa_participants,
    Components.MESSAGES: sa_messages,
}


class PostgresDataStore(DataStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = None
        # TODO qualify the columns in case of conflict
        self._list_columns = [column('conv_id')] + PostgresConversationDataStore.sa_core_property_keys

    async def prepare(self):
        if self.engine is not None:
            raise Em2Exception('postgres engine already initialised')
        logger.info('creating postgres data store connection pool')
        self.engine = await _create_engine(
            get_dsn(self.settings),
            loop=self.loop,
            minsize=self.settings.PG_POOL_MINSIZE,
            maxsize=self.settings.PG_POOL_MAXSIZE,
            timeout=self.settings.PG_POOL_TIMEOUT,
        )

    async def create_conversation(self, conn, **kwargs):
        logger.info('creating conversation %s', kwargs['conv_id'])
        # key word arguments to create_conversation exactly match the db.
        return await conn.execute(sa_conversations.insert().values(**kwargs))

    async def list_conversations(self, conn, address, limit=None, offset=None):
        j = join(sa_conversations, sa_participants, sa_conversations.c.id == sa_participants.c.conversation)
        q = (select(self._list_columns, use_labels=True)
             .select_from(j)
             .where(sa_participants.c.address == address)
             .order_by(sa_conversations.c.timestamp.desc(), sa_conversations.c.id.desc())
             .limit(limit)
             .offset(offset))
        results = []
        async for row in conn.execute(q):
            results.append(dict(row))
        return results

    @property
    def conv_data_store(self):
        return PostgresConversationDataStore

    def connection(self):
        return ConnectionContextManager(self.engine)

    async def finish(self):
        logger.warning('closing postgres data store connection pool')
        self.engine.close()
        await self.engine.wait_closed()
        self.engine = None


class ConnectionContextManager:
    def __init__(self, engine):
        self._engine = engine

    async def __aenter__(self):
        self.conn = await self._engine._acquire()
        self.tr = await self.conn._begin()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.tr.rollback()
        else:
            if self.tr.is_active:  # pragma: no branch
                await self.tr.commit()
        self.tr = None
        self._engine.release(self.conn)
        self.conn = None


class PostgresConversationDataStore(ConversationDataStore):
    sa_core_property_keys = [column(c) for c in ConversationDataStore._core_property_keys]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._local_id = None

    async def get_core_properties(self):
        q = (select(self.sa_core_property_keys)
             .where(sa_conversations.c.conv_id == self.conv)
             .order_by(sa_conversations.c.timestamp.desc()))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            raise ConversationNotFound('conversation {} not found'.format(self.conv))
        return dict(row)

    async def save_event(self, event_id, action, **data):
        kwargs = {
            'id': event_id,
            'conversation': await self._get_local_id(),
            'actor': action.participant_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': action.timestamp,
        }
        await self.conn.execute(sa_events.insert().values(**kwargs))

    async def set_published_id(self, new_timestamp, new_id):
        await self._update_conv(draft_conv_id=self.conv, conv_id=new_id, timestamp=new_timestamp)
        self.conv = new_id

    # Status

    async def set_status(self, status):
        await self._update_conv(status=status)

    # Ref

    async def set_ref(self, ref):
        await self._update_conv(ref=ref)

    # Subject

    async def set_subject(self, subject):
        await self._update_conv(subject=subject)

    async def _update_conv(self, **kwargs):
        q = (sa_conversations.update()
             .where(sa_conversations.c.conv_id == self.conv)
             .values(**kwargs))
        return await self.conn.execute(q)

    # Component generic methods

    async def add_component(self, component, **kwargs):
        if component not in {Components.PARTICIPANTS, Components.MESSAGES}:
            # FIXME logic below might well work fine but we should check explicitly
            raise NotImplementedError()
        kwargs['conversation'] = await self._get_local_id()
        sa_component = sa_component_lookup[component]
        v = await self.conn.execute(sa_component.insert().returning(sa_component.c.id).values(**kwargs))
        return (await v.first()).id

    async def edit_component(self, component, item_id, **kwargs):
        if component != Components.MESSAGES:
            # FIXME logic below might well work fine but we should check explicitly
            raise NotImplementedError()
        local_id = await self._get_local_id()
        sa_component = sa_component_lookup[component]
        q = (sa_component.update()
             .where(sa_component.c.id == item_id)
             .where(sa_component.c.conversation == local_id)
             .values(**kwargs))
        await self.conn.execute(q)

    async def delete_component(self, component, item_id):
        if component != Components.MESSAGES:
            # FIXME logic below might well work fine but we should check explicitly
            raise NotImplementedError()
        local_id = await self._get_local_id()
        sa_component = sa_component_lookup[component]
        q = (sa_component.delete()
             .where(sa_component.c.id == item_id)
             .where(sa_component.c.conversation == local_id))
        await self.conn.execute(q)

    async def lock_component(self, component, item_id):
        if component != Components.MESSAGES:  # pragma no branch
            # locking only applies to messages, method name remains in case that changes
            raise NotImplementedError()
        await self._update_message(item_id, locked=True)

    async def unlock_component(self, component, item_id):
        if component != Components.MESSAGES:  # pragma no branch
            # locking only applies to messages, method name remains in case that changes
            raise NotImplementedError()
        await self._update_message(item_id, locked=False)

    async def check_component_locked(self, component, item_id):
        local_id = await self._get_local_id()
        q = (select([sa_messages.c.locked])
             .where(sa_messages.c.conversation == local_id)
             .where(sa_messages.c.id == item_id))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            raise ComponentNotFound('message {} not found'.format(item_id))
        return row.locked

    async def get_all_component_items(self, component):
        local_id = await self._get_local_id()
        sa_component = sa_component_lookup[component]
        q = select([sa_component]).where(sa_component.c.conversation == local_id)
        # TODO can we make this into a generator or do something more efficient?
        data = []
        async for row in self.conn.execute(q):
            data.append(dict(row))
        return data

    async def get_item_last_event(self, component, item_id):
        local_id = await self._get_local_id()
        q = (select([sa_events.c.id, sa_events.c.timestamp])
             .where(sa_events.c.conversation == local_id)
             .where(sa_events.c.component == component)
             .where(sa_events.c.item == item_id)
             .order_by(sa_events.c.seq_id.desc()))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            raise EventNotFound('event for component {}:{} not found'.format(component, item_id))
        return row.id, row.timestamp

    # Messages

    async def get_message_meta(self, message_id):
        local_id = await self._get_local_id()
        q = (select([sa_messages.c.author, sa_messages.c.timestamp])
             .where(sa_messages.c.conversation == local_id)
             .where(sa_messages.c.id == message_id))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            raise ComponentNotFound('message {} not found'.format(message_id))
        return {k: row[k] for k in ('author', 'timestamp')}

    async def _update_message(self, item_id, **kwargs):
        local_id = await self._get_local_id()
        q = (sa_messages.update()
             .where(sa_messages.c.id == item_id)
             .where(sa_messages.c.conversation == local_id)
             .values(**kwargs))
        return await self.conn.execute(q)

    # Participants

    async def get_participant(self, participant_address):
        j = join(sa_participants, sa_conversations, sa_participants.c.conversation == sa_conversations.c.id)
        q = (select([sa_conversations.c.id, sa_participants.c.id, sa_participants.c.permissions], use_labels=True)
             .select_from(j)
             .where(sa_conversations.c.conv_id == self.conv)
             .where(sa_participants.c.address == participant_address)
             .order_by(sa_conversations.c.timestamp.desc()))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            # should raise ConversationNotFound if the conversation doesn't exist
            try:
                await self.get_core_properties()
            except ConversationNotFound:
                raise
            else:
                raise ComponentNotFound('participant {} not found'.format(participant_address))
        self._local_id = row.conversations_id
        return row.participants_id, row.participants_permissions

    async def _get_local_id(self):
        if self._local_id is None:
            q = (select([sa_conversations.c.id])
                 .where(sa_conversations.c.conv_id == self.conv)
                 .order_by(sa_conversations.c.timestamp.desc()))
            result = await self.conn.execute(q)
            row = await result.first()
            if row is None:
                raise ConversationNotFound('conversation {} not found'.format(self.conv))
            self._local_id = row.id
        return self._local_id
