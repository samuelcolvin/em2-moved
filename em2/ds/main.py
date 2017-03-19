"""
Abstract base for data storage in em2.

Database back-ends for em2 should define a child class for DataStore which implements all "NotImplemented" methods.
"""
from em2 import Settings
from em2.core.components import Components


class DataStore:
    def __init__(self, settings: Settings, *, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop
        super().__init__(**kwargs)

    async def create_conversation(self, conn, conv_id, creator, timestamp, ref, subject, status):
        raise NotImplementedError()

    async def startup(self):
        pass

    async def terminate(self):
        pass

    async def conversations_for_address(self, conn, address, limit=None, offset=None):
        raise NotImplementedError()

    async def all_conversations(self):
        raise NotImplementedError()

    @property
    def conv_data_store(self):
        raise NotImplementedError()

    def conn_manager(self):
        raise NotImplementedError()

    async def shutdown(self):
        pass

    def new_conv_ds(self, conv_id, conn):
        return self.conv_data_store(self, conv_id, conn)


class ConversationDataStore:
    def __init__(self, ds, conv_id, conn):
        self.ds = ds
        self.conv = conv_id
        self.conn = conn

    async def commit(self):
        raise NotImplementedError()

    async def export(self):
        data = await self.get_core_properties()

        participants_lookup = {}
        participants = []
        async for p in self.get_all_component_items(Components.PARTICIPANTS):
            participants_lookup[p['id']] = p['address']
            participants.append((p['address'], p['permissions']))

        data.update({
            # TODO signature
            Components.PARTICIPANTS: participants,
            Components.MESSAGES: [
                dict(
                    id=m['id'],
                    author=participants_lookup[m['author']],
                    timestamp=m['timestamp'],
                    body=m['body'],
                    parent=m.get('parent'),
                ) async for m in self.get_all_component_items(Components.MESSAGES)
            ],
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

    async def save_event(self, action, **data):
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

    async def set_subject(self, subject: str):
        raise NotImplementedError()

    async def get_subject(self) -> str:
        """
        Could be overwritten by subclasses to be more performant, eg. only get a single fields from the db.
        :return: the conversation's subject
        """
        props = await self.get_core_properties()
        return props['subject']

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

    async def receiving_participants(self):
        """
        Get data suitable for propagating data to participants. This is used both for em2 distribution and fallback.

        Could be overwritten by subclasses to be more performant, eg. only get the required fields from the db.

        :return: list of key information for each participant in a conversation
        """
        participants = []
        async for p in self.get_all_component_items(Components.PARTICIPANTS):
            participants.append({
                'address': p['address'],
                # 'dn': p['display_name'],  # TODO
                # 'hd': p['hidden'],  # TODO
            })
        return participants


class NullDataStore(DataStore):

    async def create_conversation(self, conn, **kwargs):
        return 0

    async def conversations_for_address(self, conn, address, limit=None, offset=None):
        return []

    async def all_conversations(self):
        return []

    @property
    def conv_data_store(self):
        return NullConversationDataStore

    def conn_manager(self):
        return VoidContextManager()


class VoidContextManager:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class NullConversationDataStore(ConversationDataStore):  # pragma: no cover
    async def get_core_properties(self):
        return {}

    async def commit(self):
        pass

    async def save_event(self, action, **data):
        pass

    async def set_published_id(self, new_timestamp, new_id):
        pass

    # Status

    async def set_status(self, status):
        pass

    # Ref

    async def set_ref(self, ref):
        pass

    # Subject

    async def set_subject(self, subject):
        pass

    # Component generic methods

    async def add_component(self, component, **kwargs):
        return 0

    async def edit_component(self, component, item_id, **kwargs):
        pass

    async def delete_component(self, component, item_id):
        pass

    async def lock_component(self, component, item_id):
        pass

    async def unlock_component(self, component, item_id):
        pass

    async def check_component_locked(self, component, item_id):
        return False

    async def get_all_component_items(self, component):
        return

    async def get_item_last_event(self, component, item_id):
        return None, None

    # Messages

    async def get_message_meta(self, message_id):
        return {}

    # Participants

    async def get_participant(self, participant_address):
        return None, None
