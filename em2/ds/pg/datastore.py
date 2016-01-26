from sqlalchemy import select, column, join

from em2.core.common import Components
from em2.core.datastore import DataStore, ConversationDataStore
from em2.core.exceptions import ConversationNotFound, ComponentNotFound

from .models import sa_conversations, sa_participants, sa_messages, sa_updates

sa_component_lookup = {
    Components.CONVERSATIONS: sa_conversations,
    Components.PARTICIPANTS: sa_participants,
    Components.MESSAGES: sa_messages,
}


class PostgresDataStore(DataStore):
    def __init__(self, engine):
        self.engine = engine

    async def create_conversation(self, conn, **kwargs):
        # key word arguments to create_conversation exactly match the db.
        return await conn.execute(sa_conversations.insert().values(**kwargs))

    @property
    def conv_data_store(self):
        return PostgresConversationDataStore

    def connection(self):
        return ConnectionContextManager(self.engine)


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
            if self.tr.is_active:
                await self.tr.commit()
        self.tr = None
        self._engine.release(self.conn)
        self.conn = None


class PostgresConversationDataStore(ConversationDataStore):
    _sa_core_property_keys = [column(c) for c in ConversationDataStore._core_property_keys]

    def __init__(self, *args, **kwargs):
        super(PostgresConversationDataStore, self).__init__(*args, **kwargs)
        self._local_id = None

    async def get_core_properties(self):
        q = (select(self._sa_core_property_keys)
             .where(sa_conversations.c.conv_id == self.conv)
             .order_by(sa_conversations.c.timestamp.desc()))
        result = await self.conn.execute(q)
        row = await result.first()
        if row is None:
            raise ConversationNotFound('conversation {} not found'.format(self.conv))
        return row

    async def save_event(self, action, data):
        kwargs = {
            'conversation': await self._get_local_id(),
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': action.timestamp,
        }
        await self.conn.execute(sa_updates.insert().values(**kwargs))

    async def set_published_id(self, new_timestamp, new_id):
        raise NotImplementedError()

    # Status

    async def set_status(self, status):
        raise NotImplementedError()

    # Ref

    async def set_ref(self, ref):
        raise NotImplementedError()

    # Subject

    async def set_subject(self, subject):
        raise NotImplementedError()

    # Component generic methods

    async def add_component(self, component, **kwargs):
        if component in {Components.PARTICIPANTS, Components.MESSAGES}:
            kwargs['conversation'] = await self._get_local_id()
            sa_component = sa_component_lookup[component]
            v = await self.conn.execute(sa_component.insert().returning(sa_component.c.id).values(**kwargs))
            return (await v.first()).id
        else:
            raise NotImplementedError()

    async def edit_component(self, component, item_id, **kwargs):
        raise NotImplementedError()

    async def delete_component(self, component, item_id):
        raise NotImplementedError()

    async def lock_component(self, component, item_id):
        raise NotImplementedError()

    async def unlock_component(self, component, item_id):
        raise NotImplementedError()

    async def check_component_locked(self, component, item_id):
        raise NotImplementedError()

    async def get_all_component_items(self, component):
        local_id = await self._get_local_id()
        sa_component = sa_component_lookup[component]
        q = select([sa_component]).where(sa_participants.c.conversation == local_id)
        data = []
        async for row in self.conn.execute(q):
            data.append(row)
        return data

    # Messages

    async def get_message_meta(self, message_id):
        raise NotImplementedError()

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
