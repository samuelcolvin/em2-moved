import logging
import hashlib

from .exceptions import (InsufficientPermissions, ComponentNotFound, ComponentNotLocked,
                         ComponentLocked, BadDataException, MisshapedDataException, DataConsistencyException)
from .common import Components
from .enums import Enum

logger = logging.getLogger('em2')


def hash_id(*args, **kwargs):
    sha256 = kwargs.pop('sha256', False)
    if kwargs != {}:  # pragma: no cover
        raise TypeError('unexpected keywords args: {}'.format(kwargs))
    to_hash = '_'.join(map(str, args))
    to_hash = to_hash.encode()
    if sha256:
        return hashlib.sha256(to_hash).hexdigest()
    else:
        return hashlib.sha1(to_hash).hexdigest()


class _Component:
    name = None

    def __init__(self, controller):
        self.controller = controller

    async def _event(self, *args, **kwargs):
        return await self.controller.event(*args, **kwargs)

    def __repr__(self):
        return '<{} on controller "{}">'.format(self.__class__.__name__, self.controller.ref)


class Messages(_Component):
    name = Components.MESSAGES

    async def add_multiple(self, ds, data):
        if data[0]['parent'] is not None:
            raise MisshapedDataException('first message parent should be None')

        parents = {data[0]['id']: data[0]['timestamp']}
        for d in data[1:]:
            if d['id'] in parents:
                raise BadDataException('message id {id} already exists'.format(**d))
            parent = parents.get(d['parent'])
            if parent is None:
                raise ComponentNotFound('message {parent} not found'.format(**d))
            if parent >= d['timestamp']:
                raise BadDataException('timestamp {timestamp} not after parent'.format(**d))
            parents[d['id']] = d['timestamp']

        participants = await ds.get_all_component_items(Components.PARTICIPANTS)
        participants = {p['address']: p['id'] for p in participants}
        for d in data:
            d['author'] = participants[d['author']]

        await ds.add_multiple_components(self.name, data)

    async def add_basic(self, action, body, parent_id):
        m_id = hash_id(action.actor_addr, action.timestamp.isoformat(), body, parent_id)
        await action.ds.add_component(
            self.name,
            id=m_id,
            author=action.actor_id,
            timestamp=action.timestamp,
            body=body,
            parent=parent_id,
        )
        return m_id

    async def add(self, action, body, parent_id):
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE access required to add messages')

        meta = await action.ds.get_message_meta(parent_id)
        if action.timestamp <= meta['timestamp']:
            raise BadDataException('timestamp not after parent timestamp: {}'.format(action.timestamp))

        if action.is_remote:
            await action.ds.add_component(
                self.name,
                id=action.item,
                author=action.actor_id,
                timestamp=action.timestamp,
                body=body,
                parent=parent_id,
            )
        else:
            action.item = await self.add_basic(action, body, parent_id)
        await self._event(action, p_parent_id=parent_id, p_body=body)

    async def edit(self, action, body):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.edit_component(self.name, action.item, body=body)
        await self._event(action, b_value=body)

    async def delta_edit(self, action, body):
        raise NotImplementedError()

    async def delete(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.delete_component(self.name, action.item)
        await self._event(action)

    async def lock(self, action):
        await self._check_permissions(action)
        await self._check_locked(action)
        await action.ds.lock_component(self.name, action.item)
        await self._event(action)

    async def unlock(self, action):
        await self._check_permissions(action)
        if not await action.ds.check_component_locked(self.name, action.item):
            raise ComponentNotLocked('{} with id = {} not locked'.format(self.name, action.item))
        await self._check_consistency(action)
        await action.ds.unlock_component(self.name, action.item)
        await self._event(action)

    async def _check_permissions(self, action):
        if action.perm == perms.WRITE:
            meta = await action.ds.get_message_meta(action.item)
            if action.actor_id != meta['author']:
                raise InsufficientPermissions('To {} a message authored by another participant '
                                              'FULL permissions are requires'.format(action.verb))
        elif action.perm != perms.FULL:
            raise InsufficientPermissions('To {} a message requires FULL or WRITE permissions'.format(action.verb))

    async def _check_locked(self, action):
        if await action.ds.check_component_locked(self.name, action.item):
            raise ComponentLocked('{} with id = {} locked'.format(self.name, action.item))
        if action.parent_event_id is None:
            raise BadDataException('parent event id should not be none to {} a message'.format(action.verb))
        await self._check_consistency(action)

    async def _check_consistency(self, action):
        last_event_id, last_event_ts = await action.ds.get_item_last_event(self.name, action.item)
        if last_event_id is None:
            return

        if action.parent_event_id != last_event_id:
            # TODO maybe we need a better way of dealing with this situation
            raise DataConsistencyException('parent event id does not match the most recent event')
        if action.timestamp <= last_event_ts:
            raise BadDataException('timestamp before parent')


class Participants(_Component):
    name = Components.PARTICIPANTS

    class Permissions(Enum):
        FULL = 'full'
        WRITE = 'write'
        COMMENT = 'comment'
        READ = 'read'

    async def add_multiple(self, ds, data):
        # TODO validate
        prepared_data = [{'address': address, 'permissions': permissions} for address, permissions in data]
        await ds.add_multiple_components(self.name, prepared_data)
        for address, _ in data:
            await self.controller.prop.add_participant(ds.conv, address)

    async def add_first(self, ds, address):
        new_participant_id = await ds.add_component(
            self.name,
            address=address,
            permissions=perms.FULL,
        )
        logger.info('first participant added to %d: address: "%s"', ds.conv, address)
        return new_participant_id

    async def add(self, action, address, permissions):
        if action.perm not in {perms.FULL, perms.WRITE}:
            raise InsufficientPermissions('FULL or WRITE permission are required to add participants')
        if action.perm == perms.WRITE and permissions == perms.FULL:
            raise InsufficientPermissions('FULL permission are required to add participants with FULL permissions')
        # TODO check the address is valid
        action.item = await action.ds.add_component(
            self.name,
            address=address,
            permissions=permissions,
        )
        logger.info('added participant to %d: address: "%s", permissions: "%s"', action.conv, address, permissions)
        await self.controller.prop.add_participant(action.conv, address)
        await self._event(action)
        return action.item

# shortcut
perms = Participants.Permissions
