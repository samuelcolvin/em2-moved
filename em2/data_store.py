"""
Abstract base for data storage in em2.

Database back-ends for em2 should define a child class for DataStore which implements all "NotImplemented" methods.
"""
import logging
from .common import Components

logger = logging.getLogger('em2')


class DataStore:
    async def create_conversation(self, **kwargs):
        raise NotImplementedError()

    @property
    def con_data_store(self):
        raise NotImplementedError()

    def new_con_ds(self, con_id):
        return self.con_data_store(self, con_id)


class ConversationDataStore:
    def __init__(self, ds, con_id):
        self.ds = ds
        self.con = con_id

    async def export(self):
        data = await self.get_core_properties()
        participants = await self.get_all_component_items(Components.PARTICIPANTS)
        messages = await self.get_all_component_items(Components.MESSAGES)
        data.update({
            # TODO signature
            Components.PARTICIPANTS: [(p['address'], p['permissions']) for p in participants],
            Components.MESSAGES: messages,
            # TODO labels
            # TODO attachments
            # TODO extras
            # TODO updates
        })
        return data

    async def get_core_properties(self):
        """
        Should return dict containing:
        * timestamp
        * status
        * ref
        * subject
        * creator
        * expiration
        """
        raise NotImplementedError()

    async def save_event(self, action, data, timestamp):
        raise NotImplementedError()

    async def set_published_id(self, new_timestamp, new_id):
        raise NotImplementedError()

    # Status

    async def set_status(self, status):
        raise NotImplementedError()

    async def get_status(self):
        core_props = await self.get_core_properties()
        return core_props['status']

    # Ref

    async def set_ref(self, ref):
        raise NotImplementedError()

    async def get_ref(self):
        core_props = await self.get_core_properties()
        return core_props['ref']

    # Subject

    async def set_subject(self, subject):
        raise NotImplementedError()

    # Component generic methods

    async def add_component(self, component, **kwargs):
        raise NotImplementedError()

    async def add_multiple_components(self, component, data):
        for kwargs in data:
            await self.add_component(component, **kwargs)

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
        raise NotImplementedError()

    # Messages

    async def get_message_meta(self, message_id):
        """
        Find message author by global id, should raise ComponentNotFound if not.
        :param message_id: id of message
        :return: dict containing: participant id, timestamp
        """
        raise NotImplementedError()

    # Participants

    async def get_participant_count(self):
        """
        Find the number of participants in a con.
        """
        raise NotImplementedError()

    async def get_participant(self, participant_address):
        """
        Find a participant by address returning id and permissions, should raise ComponentNotFound if
        participant is not in the conversation.
        :param participant_address: public address of participant to find
        :return: tuple (id - local id participant, permissions - participants permissions)
        """
        raise NotImplementedError()
