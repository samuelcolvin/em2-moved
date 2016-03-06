import logging
import datetime
import inspect

import pytz

from .exceptions import ComponentNotFound, VerbNotFound, BadDataException, BadHash
from .datastore import DataStore
from .propagator import BasePropagator
from .components import Components, Messages, Participants
from .conversations import Conversations
from .interactions import Action, Verbs

logger = logging.getLogger('em2')


class Controller:
    """
    Top level class for accessing conversations and conversation components.
    """
    def __init__(self, datastore, propagator, timezone_name='utc', ref=None):
        assert isinstance(datastore, DataStore)
        assert isinstance(propagator, BasePropagator)
        self.ds = datastore
        self.prop = propagator
        self.timezone_name = timezone_name
        self.ref = ref if ref is not None else hex(id(self))
        self.conversations = Conversations(self)
        components = [Messages, Participants]
        self.components = {c.name: c(self) for c in components}
        self.valid_verbs = set(Verbs.__values__)

    async def act(self, action, **kwargs):
        """
        Routes actions to the appropriate component and executes the right verb.
        :param action: action instance
        :param kwargs: extra key word arguments to pass to the method with action
        :return: result of method associated with verb
        """
        assert isinstance(action, Action)
        if action.component == Components.CONVERSATIONS:
            component_cls = self.conversations
        else:
            component_cls = self.components.get(action.component)
            if component_cls is None:
                raise ComponentNotFound('{} is not a valid component'.format(action.component))

        if action.verb not in self.valid_verbs:
            raise VerbNotFound('{} is not a valid verb, verbs: {}'.format(action.verb, self.valid_verbs))

        if action.is_remote:
            if action.event_id != action.calc_event_id():
                raise BadHash('event_id "{}" incorrect'.format(action.event_id))
            if not isinstance(action.timestamp, datetime.datetime):
                raise BadDataException('remote actions should always have a timestamp')
        else:
            action.timestamp = self.now_tz()

        if action.component == Components.CONVERSATIONS and action.verb == Verbs.ADD:
            # this is a special case, where we don't have an existing conversation, also func arguments differ
            if action.is_remote:
                func = component_cls.add_remote
            else:
                func = component_cls.add_local
            self._check_arguments(func, kwargs, allow_subset=True)
            return await func(action, **kwargs)

        func = getattr(component_cls, action.verb, None)
        if func is None:
            raise VerbNotFound('{} is not an available verb on {}'.format(action.verb, action.component))

        self._check_arguments(func, kwargs)

        async with self.ds.connection() as conn:
            action.cds = self.ds.new_conv_ds(action.conv, conn)
            await action.prepare()
            return await func(action, **kwargs)

    @staticmethod
    def _check_arguments(func, kwargs, allow_subset=False):
        """
        Check kwargs passed match the signature of the function. This is a slight hack but is required since we can't
        catching argument mismatches without catching all TypeErrors which is worse.
        """
        expected_args = set(inspect.signature(func).parameters)
        expected_args.remove('action')
        kw_set = set(kwargs)
        if allow_subset and kw_set.issubset(expected_args):
            return
        if expected_args != set(kwargs):
            msg = 'Wrong kwargs for {}, got: {}, expected: {}'
            func_name = getattr(func, 'verb_name', func.__name__)
            raise BadDataException(msg.format(func_name, sorted(list(kwargs)), sorted(list(expected_args))))

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.utcnow())

    def _subdict(self, data, first_chars):
        return {k[2:]: v for k, v in data.items() if k[0] in first_chars}

    async def event(self, action, **data):
        """
        Record and propagate updates of conversations and conversation components.

        :param action: Action instance
        :param data: extra information to either be saved (s_*), propagated (p_*) or both (b_*)
        """
        logger.debug('event on %d: author: "%s", action: "%s", component: %s %s',
                     action.conv, action.actor_addr, action.verb, action.component, action.item)
        save_data = self._subdict(data, 'sb')
        event_id = action.calc_event_id()
        await action.cds.save_event(event_id, action, save_data)
        status = await action.cds.get_status()
        if status == Conversations.Status.DRAFT:
            return
        # TODO some way to propagate events to clients here
        if action.is_remote:
            return
        propagate_data = self._subdict(data, 'pb')
        # FIXME what happens when propagation fails, perhaps save status on update
        await self.prop.propagate(action, event_id, propagate_data, action.timestamp)

    def __repr__(self):
        return '<Controller({})>'.format(self.ref)
