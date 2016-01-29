import datetime
import pytest
from em2.core.base import Conversations, perms, Action, Verbs
from em2.core.common import Components
from em2.core.exceptions import ComponentNotFound, ConversationNotFound
from tests.conftest import datetime_tz


async def test_create_conversation(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        await ds.create_conversation(
            conn,
            conv_id='123',
            creator='test@example.com',
            timestamp=timestamp,
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
    await ds.create_conversation(
        conn,
        conv_id=conv_id,
        creator='test@example.com',
        timestamp=datetime_tz(),
        ref='x',
        subject='sub',
        status=Conversations.Status.ACTIVE,
    )
    return ds.new_conv_ds(conv_id, conn)


async def test_create_first_participant(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        assert isinstance(pid, int)


async def test_get_participant(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
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


async def test_save_event(get_ds, datastore_cls, timestamp):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        pid = await cds.add_component(
            Components.PARTICIPANTS,
            address='test@example.com',
            permissions=perms.FULL,
        )
        action = Action('test@example.com', '123', Verbs.ADD, Components.PARTICIPANTS, pid, timestamp)
        action.actor_id, action.perm = pid, perms.FULL
        await cds.save_event('event_1', action, {})

        await cds.save_event('event_2', action, {'value': 'foobar'})

        # FIXME currently there are no api methods for returning updates and it's therefore not possible to check
        # these actions are saved correctly

        # NOTE: action action.conv_id is ignored in save_event and the cds conv_id is used instead
        cds2 = ds.new_conv_ds('bad', conn)
        action.actor_id, action.perm = pid, perms.FULL
        with pytest.raises(ConversationNotFound):
            await cds2.save_event('event_3', action, {})


async def test_set_published_id(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
    async with ds.connection() as conn:
        cds = await create_conv(conn, ds)
        assert cds.conv == '123'
        new_ts = datetime_tz(2)

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


async def test_set_status_ref_subject(get_ds, datastore_cls):
    ds = await get_ds(datastore_cls)
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
