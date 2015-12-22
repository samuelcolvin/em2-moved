import datetime
import hashlib
import pytz
import logging

logger = logging.getLogger('em2')


class DataStore:
    timezone_name = 'utc'

    def __init__(self, change_handler=None):
        self.change_handler = change_handler

    def hash(self, *args, **kwargs):
        method = kwargs.pop('method', 'sha1')
        assert len(kwargs) == 0, 'unexpected keywords args: {}'.format(kwargs)
        function = getattr(hashlib, method)
        to_hash = '_'.join(map(str, args))
        return function(to_hash.encode()).hexdigest()

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    def create_conversation(self, **kwargs):
        raise NotImplementedError()

    def create_component(self, model, **kwargs):
        raise NotImplementedError()

    def record_change(self, conversation, author, action, focus_id, focus):
        # changes are always recorded but can be cleared before publish
        logger.debug('change occurred on %d: author: "%s", action: "%s", focus: %s %s',
                     conversation, author, action, focus, focus_id)
        if self.change_handler:
            self.change_handler(author, action, focus, focus_id)

    def get_message_count(self, con):
        """
        Find the number of messages associated with a conversation.
        """
        raise NotImplementedError()

    def check_message_exists(self, con, message_id):
        """
        Check a message with given id exists, should raise ComponentNotFound if not. return True if it does.
        """
        raise NotImplementedError()

    def get_participant_id(self, con, participant_email):
        """
        Get id of participant by email, should raise ComponentNotFound if participant is not on the conversation.
        """
        raise NotImplementedError()
