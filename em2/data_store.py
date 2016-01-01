"""
Abstract base for data storage in em2.

Database back-ends for em2 should define a child class for DataStore which implements all "NotImplemented" methods.
"""
import hashlib
import logging

logger = logging.getLogger('em2')


class DataStore:
    def hash(self, *args, **kwargs):
        method = kwargs.pop('method', 'sha1')
        assert len(kwargs) == 0, 'unexpected keywords args: {}'.format(kwargs)
        func = getattr(hashlib, method)
        to_hash = '_'.join(map(str, args))
        return func(to_hash.encode()).hexdigest()

    async def save_event(self, *args):
        raise NotImplementedError()

    async def create_conversation(self, **kwargs):
        raise NotImplementedError()

    async def set_status(self, conversation, status):
        raise NotImplementedError()

    async def add_component(self, model, conversation, **kwargs):
        raise NotImplementedError()

    async def edit_component(self, model, conversation, item_id, **kwargs):
        raise NotImplementedError()

    async def delete_component(self, model, conversation, item_id):
        raise NotImplementedError()

    async def lock_component(self, model, conversation, item_id):
        raise NotImplementedError()

    async def unlock_component(self, model, conversation, item_id):
        raise NotImplementedError()

    async def get_message_locked(self, model, conversation, item_id):
        raise NotImplementedError()

    async def get_message_count(self, con):
        """
        Find the number of messages associated with a conversation.
        """
        raise NotImplementedError()

    async def get_participant_count(self, conversation):
        """
        Find the number of participants in a conversation.
        """
        raise NotImplementedError()

    async def get_message_author(self, conversation, message_id):
        """
        Find message author by global id, should raise ComponentNotFound if not.
        :param conversation: local id of conversation
        :param message_id: id of message
        :return: participant id of message
        """
        # TODO, may be better to update this method to return more information
        raise NotImplementedError()

    async def get_participant(self, conversation, participant_address):
        """
        Find a participant by address returning id and permissions, should raise ComponentNotFound if
        participant is not in the conversation.
        :param conversation: local id of conversation
        :param participant_address: public address of participant to find
        :return: tuple (id - local id participant, permissions - participants permissions)
        """
        raise NotImplementedError()
