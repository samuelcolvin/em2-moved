"""
Abstract base for data storage in em2.

Database back-ends for em2 should define a child class for DataStore which implements all "NotImplemented" methods.
"""
import logging
from copy import deepcopy
from .common import Components

logger = logging.getLogger('em2')


class DataStore:
    async def create_conversation(self, conn, conv_id, creator, timestamp, ref, subject, status):
        raise NotImplementedError()

    async def list_conversations(self, user_id, limit=None, offset=None):
        raise NotImplementedError()

    @property
    def conv_data_store(self):
        raise NotImplementedError()

    def connection(self):
        raise NotImplementedError()

    async def finish(self):
        pass

    def reuse_connection(self):
        """
        Only used for tests, should return the connection previously returned from connection()
        """
        raise NotImplementedError()

    def new_conv_ds(self, conv_id, conn):
        return self.conv_data_store(self, conv_id, conn)


class ConversationDataStore:
    def __init__(self, ds, conv_id, conn):
        self.ds = ds
        self.conv = conv_id
        self.conn = conn

    async def export(self):
        data = await self.get_core_properties()
        participants_data = await self.get_all_component_items(Components.PARTICIPANTS)

        participants_lookup = {}
        participants = []
        for p in participants_data:
            participants_lookup[p['id']] = p['address']
            participants.append((p['address'], p['permissions']))

        messages = deepcopy(await self.get_all_component_items(Components.MESSAGES))
        for m in messages:
            m['author'] = participants_lookup[m['author']]

        data.update({
            # TODO signature
            Components.PARTICIPANTS: participants,
            Components.MESSAGES: messages,
            # TODO labels
            # TODO attachments
            # TODO extras
            # TODO updates
        })
        return data

    _core_property_keys = ['timestamp', 'status', 'ref', 'subject', 'creator', 'expiration']

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

    async def save_event(self, event_id, action, data):
        raise NotImplementedError()

    async def set_published_id(self, new_timestamp, new_id):
        self.conv = new_id
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
        # TODO we could remove this and make lock and unlock check themselves
        raise NotImplementedError()

    async def get_all_component_items(self, component):
        raise NotImplementedError()

    async def get_item_last_event(self, component, item_id):
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

    async def get_participant(self, participant_address):
        """
        Find a participant by address returning id and permissions, should raise ComponentNotFound if
        participant is not in the conversation.
        :param participant_address: public address of participant to find
        :return: tuple (id - local id participant, permissions - participants permissions)
        """
        raise NotImplementedError()
