"""
Synchronous interface to em2
"""
import logging

logger = logging.getLogger('em2')


class Action:
    ADD = 'add'
    EDIT = 'edit'
    DELTA_EDIT = 'delta_edit'
    DELETE = 'delete'
    LOCK = 'lock'


class Conversations:
    model = 'conversations'
    event = None

    def __init__(self, data_store):
        self.ds = data_store
        self.messages = Messages(data_store)
        self.participants = Participants(data_store)

    class Status:
        DRAFT = 'draft'
        PENDING = 'pending'
        ACTIVE = 'active'
        EXPIRED = 'expired'
        DELETED = 'deleted'

    async def create(self, creator, subject, body=None):
        timestamp = self.ds.now_tz()
        global_id = self.ds.hash(creator, timestamp.isoformat(), subject, method='sha256')
        local_id = await self.ds.create_conversation(
            global_id=global_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.DRAFT,
        )
        logger.info('created conversation: %s..., id: %d, creator: "%s", subject: "%s"',
                    global_id[:6], local_id, creator, subject)
        await self.participants.add(local_id, creator, Participants.Permissions.FULL)
        if body is not None:
            await self.messages.add(local_id, creator, body)
        return local_id

    async def publish(self):
        raise NotImplemented

    async def get_by_global_id(self, id):
        raise NotImplemented


class _Components:
    model = None

    def __init__(self, data_store):
        self.ds = data_store

    async def event(self, con, author, action, ts=None, focus_id=None, **data):
        return await self.ds.event(
            conversation=con,
            author=author,
            action=action,
            data=data,
            timestamp=ts or self.ds.now_tz(),
            focus_id=focus_id,
            focus=self.model
        )

    async def _add(self, conversation, **kwargs):
        return await self.ds.add_component(self.model, conversation, **kwargs)

    async def _edit(self, conversation, id, **kwargs):
        return await self.ds.edit_component(self.model, conversation, id, **kwargs)


class Messages(_Components):
    model = 'messages'

    async def add(self, con, author, body, parent=None):
        if parent is None:
            existing_messages = await self.ds.get_message_count(con)
            assert existing_messages == 0, '%d existing messages with blank parent' % existing_messages
        else:
            await self.ds.check_message_exists(con, parent)
        timestamp = self.ds.now_tz()
        id = self.ds.hash(author, timestamp.isoformat(), body, parent)
        await self._add(
            con,
            id=id,
            author=await self.ds.get_participant_id(con, author),
            timestamp=timestamp,
            body=body,
            parent=parent,
        )
        logger.info('added message to %d: %s..., author: "%s", parent: "%s"', con, id[:6], author, parent)
        await self.event(con, author, Action.ADD, ts=timestamp, focus_id=id)

    async def edit(self, con, author, body, message_id):
        await self.ds.check_message_exists(con, message_id)
        await self._edit(
            con,
            message_id,
            body=body,
        )
        logger.info('edited message on %d: %s..., author: "%s"', con, message_id[:6], author)
        await self.event(con, author, Action.EDIT, focus_id=message_id, value=body)


class Participants(_Components):
    model = 'participants'

    class Permissions:
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    async def add(self, con, email, permissions):
        await self._add(
            con,
            email=email,
            permissions=permissions,
        )
        logger.info('added participant to %d: email: "%s", permissions: "%s"', con, email, permissions)
        await self.event(con, email, Action.ADD)
