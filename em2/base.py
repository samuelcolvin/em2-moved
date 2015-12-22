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
    record_change = None

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
        self.participants.create(local_id, creator)
        if body is not None:
            self.messages.create(local_id, creator, body)
        return local_id

    def publish(self):
        pass

    def get_by_global_id(self, id):
        pass


class _Components:
    model = None

    def __init__(self, data_store):
        self.ds = data_store

    def record_change(self, con, author, action, focus_id=None):
        self.ds.record_change(con, author, action, focus_id, focus=self.model)

    def _create(self, conversation, **kwargs):
        return self.ds.create_component(
            self.model,
            conversation=conversation,
            **kwargs
        )


class Messages(_Components):
    model = 'messages'

    def create(self, con, author, body, parent=None):
        if parent is None:
            existing_messages = self.ds.get_message_count(con)
            assert existing_messages == 0, '%d existing messages with blank parent' % existing_messages
        else:
            assert self.ds.check_message_exists(con, parent)
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
        self.record_change(con, author, Action.CREATE, id)


class Participants(_Components):
    model = 'participants'

    class Permissions:
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    def create(self, con, email, permissions=None):
        permissions = permissions or self.Permissions.FULL
        self._create(
            con,
            email=email,
            permissions=permissions,
        )
        logger.info('created participant on %d: email: "%s", permissions: "%s"', con, email, permissions)
        self.record_change(con, email, Action.CREATE)
