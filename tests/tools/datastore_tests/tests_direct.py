import datetime
import pytest
from em2.core.base import Conversations, perms, Action, Verbs
from em2.core.common import Components
from em2.core.exceptions import ComponentNotFound


async def test_create_conversation(data_store):
    async with data_store.connection() as conn:
        ts = datetime.datetime.now()
        await data_store.create_conversation(
            conn,
            conv_id='123',
            creator='test@example.com',
            timestamp=ts,
            ref='x',
            subject='sub',
            status=Conversations.Status.ACTIVE,
        )
        cds = data_store.new_conv_ds('123', conn)
        props = await cds.get_core_properties()
        props = dict(props)
        ts = props.pop('timestamp')
        assert isinstance(ts, datetime.datetime)
        assert props == {
            'subject': 'sub',
            'creator': 'test@example.com',
            'status': 'active',
            'ref': 'x',
            'expiration': None,
        }


async def create_conv(conn, data_store, conv_id='123'):
    ts = datetime.datetime.now()
    await data_store.create_conversation(
        conn,
        conv_id=conv_id,
        creator='test@example.com',
        timestamp=ts,
        ref='x',
        subject='sub',
        status=Conversations.Status.ACTIVE,
    )
    return data_store.new_conv_ds(conv_id, conn)


async def test_create_first_participant(data_store):
    async with data_store.connection() as conn:
        cds = await create_conv(conn, data_store)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        assert isinstance(pid, int)


async def test_get_participant(data_store):
    async with data_store.connection() as conn:
        cds = await create_conv(conn, data_store)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        assert isinstance(pid, int)
        pid2, perm = await cds.get_participant('test@example.com')
        assert perm == perms.FULL
        assert pid2 == pid
        with pytest.raises(ComponentNotFound):
            await cds.get_participant('foo@example.com')


async def test_save_event(data_store):
    async with data_store.connection() as conn:
        cds = await create_conv(conn, data_store)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        ts = datetime.datetime.now()
        action = Action('test@example.com', '123', Verbs.ADD, Components.PARTICIPANTS, pid, ts)
        action.actor_id, action.perm = pid, perms.FULL
        await cds.save_event(action, {})

        await cds.save_event(action, {'value': 'foobar'})

        # FIXME currently there are no api methods for returning updates and it's therefore not possible to check
        # these actions are saved correctly
