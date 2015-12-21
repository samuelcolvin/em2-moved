"""
Synchronous interface to em2
"""
import datetime
import hashlib
import pytz


class Action:
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    LOCK = 'lock'


class Components:
    model = None
    actions = set()

    def __init__(self, ctx):
        self._ctx = ctx

    def hash(self, *args, **kwargs):
        method = kwargs.pop('method', 'sha1')
        assert len(kwargs) == 0, 'unexpected keywords args: {}'.format(kwargs)
        function = getattr(hashlib, method)
        to_hash = '_'.join(map(str, args))
        return function(to_hash).hexdigest()

    @property
    def timezone(self):
        return pytz.timezone(self._ctx.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    def record_update(self, author, action, focus_id=None):
        self._ctx.update(author, action, self.model, focus_id)


class Messages(Components):
    model = 'message'
    actions = {Action.CREATE, Action.UPDATE, Action.DELETE, Action.LOCK}

    def create(self, conversation, author, body, parent=None):
        if parent is None:
            # TODO check we have no previous messages
            pass
        timestamp = self.now_tz()
        id = self.hash(author, timestamp.isoformat(), body, parent)
        self._ctx.create(
            self.model,
            conversation=conversation,
            id=id,
            author=author,
            timestamp=timestamp,
            body=body,
            parent=parent,
        )
        self.record_update(author, Action.CREATE, id)


class Participants(Components):
    model = 'participant'
    actions = {Action.CREATE, Action.UPDATE, Action.DELETE}


class Conversations(Components):
    model = 'conversation'
    record_update = None

    class Status:
        DRAFT = 'draft'
        PENDING = 'pending'
        ACTIVE = 'active'
        EXPIRED = 'expired'
        DELETED = 'deleted'

    def create(self, creator, subject):
        timestamp = self.now_tz()
        global_id = self.hash(creator, timestamp.isoformat(), subject, method='sha256')
        con_id = self._ctx.create(
            self.model,
            global_id=global_id,
            timestamp=timestamp,
            creator=creator,
            subject=subject,
            status=self.Status.DRAFT,
        )
        self._ctx.messages.create()
        return con_id

    def publish(self):
        pass

    def get_by_global_id(self, id):
        pass


class Context:
    timezone_name = 'utc'

    def __init__(self):
        self.conversations = Conversations(self)
        self.messages = Messages(self)
        self.participants = Participants(self)

    def create(self, model, *args, **kwargs):
        raise NotImplementedError()

    def update(self, author, action, focus, focus_id=None):
        raise NotImplementedError()
