"""
Synchronous interface to em2
"""
import logging

logger = logging.getLogger('em2')


class Action:
    CREATE = 'create'
    UPDATE = 'update'
    UPDATE_DELTA = 'update_delta'
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

    def create(self, creator, subject, body=None):
        timestamp = self.ds.now_tz()
        global_id = self.ds.hash(creator, timestamp.isoformat(), subject, method='sha256')
        local_id = self.ds.create_conversation(
            global_id=global_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.DRAFT,
        )
        logger.info('created conversation: %s..., id: %d, creator: "%s", subject: "%s"',
                    global_id[:6], local_id, creator, subject)
        self.participants.create(local_id, creator, Participants.Permissions.FULL)
        if body is not None:
            self.messages.create(local_id, creator, body)
        return local_id

    def publish(self):
        raise NotImplemented

    def get_by_global_id(self, id):
        raise NotImplemented


class _Components:
    model = None

    def __init__(self, data_store):
        self.ds = data_store

    def event(self, con, author, action, ts=None, focus_id=None, **data):
        self.ds.event(
            conversation=con,
            author=author,
            action=action,
            data=data,
            timestamp=ts or self.ds.now_tz(),
            focus_id=focus_id,
            focus=self.model
        )

    def _create(self, conversation, **kwargs):
        return self.ds.create_component(self.model, conversation, **kwargs)

    def _update(self, conversation, id, **kwargs):
        return self.ds.update_component(self.model, conversation, id, **kwargs)


class Messages(_Components):
    model = 'messages'

    def create(self, con, author, body, parent=None):
        if parent is None:
            existing_messages = self.ds.get_message_count(con)
            assert existing_messages == 0, '%d existing messages with blank parent' % existing_messages
        else:
            self.ds.check_message_exists(con, parent)
        timestamp = self.ds.now_tz()
        id = self.ds.hash(author, timestamp.isoformat(), body, parent)
        self._create(
            con,
            id=id,
            author=self.ds.get_participant_id(con, author),
            timestamp=timestamp,
            body=body,
            parent=parent,
        )
        logger.info('created message on %d: %s..., author: "%s", parent: "%s"', con, id[:6], author, parent)
        self.event(con, author, Action.CREATE, ts=timestamp, focus_id=id)

    def update(self, con, author, body, message_id):
        self.ds.check_message_exists(con, message_id)
        self._update(
            con,
            message_id,
            body=body,
        )
        logger.info('updated message on %d: %s..., author: "%s"', con, message_id[:6], author)
        self.event(con, author, Action.UPDATE, focus_id=message_id, value=body)


class Participants(_Components):
    model = 'participants'

    class Permissions:
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    def create(self, con, email, permissions):
        self._create(
            con,
            email=email,
            permissions=permissions,
        )
        logger.info('created participant on %d: email: "%s", permissions: "%s"', con, email, permissions)
        self.event(con, email, Action.CREATE)
