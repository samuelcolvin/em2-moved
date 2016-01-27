import datetime
import pytest
from em2.core.base import Conversations, perms, Action, Verbs
from em2.core.common import Components
from em2.core.exceptions import ComponentNotFound
from tests.conftest import timestamp


async def test_create_conversation(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        ts = datetime.datetime.now()
        await ds.create_conversation(
            conn,
            conv_id='123',
            creator='test@example.com',
            timestamp=ts,
            ref='x',
            subject='sub',
            status=Conversations.Status.ACTIVE,
        )
        cds = ds.new_conv_ds('123', conn)
        props = await cds.get_core_properties()
        props = dict(props)
        ts = props.pop('timestamp')
        assert isinstance(ts, datetime.datetime)
        assert props == {
            'subject': 'sub',
            'creator': 'test@example.com',
            'status': Conversations.Status.ACTIVE,
            'ref': 'x',
            'expiration': None,
        }


async def create_conv(conn, ds, conv_id='123'):
    ts = datetime.datetime.now()
    await ds.create_conversation(
        conn,
        conv_id=conv_id,
        creator='test@example.com',
        timestamp=ts,
        ref='x',
        subject='sub',
        status=Conversations.Status.ACTIVE,
    )
    return ds.new_conv_ds(conv_id, conn)


async def test_create_first_participant(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        assert isinstance(pid, int)


async def test_get_participant(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
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


async def test_save_event(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
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


async def test_set_published_id(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        assert cds.conv == '123'
        new_ts = timestamp()

        props = await cds.get_core_properties()
        # to avoid issue with tzinfo=psycopg2.tz...
        assert props['timestamp'].isoformat() != new_ts.isoformat()

        await cds.set_published_id(new_ts, '456')
        props = await cds.get_core_properties()
        props = dict(props)
        ts = props.pop('timestamp')
        assert ts.isoformat() == new_ts.isoformat()
        assert props == {
            'subject': 'sub',
            'creator': 'test@example.com',
            'status': Conversations.Status.ACTIVE,
            'ref': 'x',
            'expiration': None,
        }
        assert cds.conv == '456'


async def test_set_status_ref_subject(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        cds2 = await create_conv(conn, ds, conv_id='other')

        props = await cds.get_core_properties()
        assert props['status'] == Conversations.Status.ACTIVE
        assert props['ref'] == 'x'
        assert props['subject'] == 'sub'

        props = await cds2.get_core_properties()
        assert props['status'] == Conversations.Status.ACTIVE
        assert props['ref'] == 'x'
        assert props['subject'] == 'sub'

        await cds.set_status(Conversations.Status.EXPIRED)
        await cds.set_ref('foobar')
        await cds.set_subject('different subject')

        props = await cds.get_core_properties()
        assert props['status'] == Conversations.Status.EXPIRED
        assert props['ref'] == 'foobar'
        assert props['subject'] == 'different subject'

        # check the other conversation is unchanged
        props = await cds2.get_core_properties()
        assert props['status'] == Conversations.Status.ACTIVE
        assert props['ref'] == 'x'
        assert props['subject'] == 'sub'


async def test_add_component_message(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        ts = timestamp()
        await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=ts,
            body='hello',
            parent=None,
        )
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        message = dict(messages[0])
        assert message['timestamp'].isoformat() == ts.isoformat()
        assert message['id'] == 'm123'
        assert message['author'] == pid
        assert message['body'] == 'hello'
        assert message['parent'] is None
        # TODO test other things eg. locked


async def test_edit_component_message(get_ds):
    ds = await get_ds()
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        ts = timestamp()
        local_id = await cds.add_component(
            Components.MESSAGES,
            id='m123',
            author=pid,
            timestamp=ts,
            body='hello',
            parent=None,
        )
        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        assert messages[0]['timestamp'].isoformat() == ts.isoformat()
        assert messages[0]['id'] == 'm123'
        assert messages[0]['body'] == 'hello'

        await cds.edit_component(
            Components.MESSAGES,
            local_id,
            body='this is a different body',
        )

        messages = await cds.get_all_component_items(Components.MESSAGES)
        assert len(messages) == 1
        assert messages[0]['timestamp'].isoformat() == ts.isoformat()
        assert messages[0]['id'] == 'm123'
        assert messages[0]['body'] == 'this is a different body'
