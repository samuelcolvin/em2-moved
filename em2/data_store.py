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
        func = getattr(hashlib, method)
        to_hash = '_'.join(map(str, args))
        return func(to_hash.encode()).hexdigest()

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    async def create_conversation(self, **kwargs):
        raise NotImplementedError()

    async def create_component(self, model, conversation, **kwargs):
        raise NotImplementedError()

    async def update_component(self, model, conversation, item_id, **kwargs):
        raise NotImplementedError()

    async def event(self, conversation, author, action, data, timestamp, focus_id, focus):
        """
        Record and propagate update of conversations and creation, update and deletion or conversation components.

        :param conversation: local id of conversation event occurred on
        :param author: participant id of event author
        :param action: see base.Action
        :param data: extra information associated with the update
        :param timestamp: datetime the update occurred
        :param focus_id: id of item created or modified
        :param focus: model name of item being updated
        :return: None
        """
        # changes are always recorded but can be cleared before publish
        logger.debug('change occurred on %d: author: "%s", action: "%s", focus: %s %s',
                     conversation, author, action, focus, focus_id)
        await self.save_event(conversation, author, action, data, timestamp, focus_id, focus)
        if self.change_handler:
            await self.change_handler(conversation, author, action, timestamp, focus_id, focus)

    async def save_event(self, *args):
        raise NotImplementedError()

    async def get_message_count(self, con):
        """
        Find the number of messages associated with a conversation.
        """
        raise NotImplementedError()

    async def check_message_exists(self, con, message_id):
        """
        Check a message with given id exists, should raise ComponentNotFound if not. return True if it does.
        """
        raise NotImplementedError()

    async def get_participant_id(self, con, participant_addre):
        """
        Get id of participant by addre, should raise ComponentNotFound if participant is not on the conversation.
        """
        raise NotImplementedError()
