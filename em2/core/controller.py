import logging
import datetime
import inspect

import pytz

from .exceptions import ComponentNotFound, VerbNotFound, BadDataException, BadHash
from .datastore import DataStore
from .propagator import BasePropagator
from .components import Components, Messages, Participants
from .conversations import Conversations
from .interactions import Action, Verbs, Retrieval, RVerbs

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

    async def act(self, action: Action, **kwargs):
        """
        Routes actions to the appropriate component and executes the right verb.
        :param action: action instance
        :param kwargs: extra key word arguments to pass to the method with action
        :return: result of method associated with verb
        """
        assert isinstance(action, Action)

        if Verbs.get_attr(action.verb) is None:
            raise VerbNotFound('{} is not a valid verb, verbs: {}'.format(action.verb, Verbs.__values__))

        if action.is_remote:
            if action.event_id != action.calc_event_id():
                raise BadHash('event_id "{}" incorrect'.format(action.event_id))
            if not isinstance(action.timestamp, datetime.datetime):
                raise BadDataException('remote actions should always have a timestamp')
        else:
            action.timestamp = self.now_tz()

        func = self._get_function(action, Verbs)
        self._check_arguments(func, kwargs)

        async with self.ds.connection() as conn:
            if action.known_conversation:
                action.cds = self.ds.new_conv_ds(action.conv, conn)
                await action.set_participant()
                return await func(action, **kwargs)
            else:
                action.conn = conn
                return await func(action, **kwargs)

    async def retrieve(self, retrieval: Retrieval, **kwargs):
        """
        Routes retrieval to the appropriate component and executes the right verb.
        :param retrieval: retrieval instance
        :param kwargs: extra key word arguments to pass to the method with retrieval
        :return: result of method associated with verb
        """
        func = self._get_function(retrieval, RVerbs)

        self._check_arguments(func, kwargs)

        async with self.ds.connection() as conn:
            if retrieval.known_conversation:
                retrieval.cds = self.ds.new_conv_ds(retrieval.conv, conn)
                await retrieval.set_participant()
                return await func(retrieval, **kwargs)
            else:
                retrieval.conn = conn
                return await func(retrieval, **kwargs)

    def _get_function(self, inter, enum):
        component_cls = self._get_component(inter.component)

        if enum.get_attr(inter.verb) is None:
            raise VerbNotFound('{} is not a valid verb, verbs: {}'.format(inter.verb, enum.__values__))

        for func_name in self._function_names(inter.verb, inter.is_remote):
            func = getattr(component_cls, func_name, None)
            if func:
                return func
        raise VerbNotFound('{} is not an available verb on {}'.format(inter.verb, inter.component))

    def _get_component(self, component_name):
        if component_name == Components.CONVERSATIONS:
            component_cls = self.conversations
        else:
            component_cls = self.components.get(component_name)
            if component_cls is None:
                raise ComponentNotFound('{} is not a valid component'.format(component_name))
        return component_cls

    @staticmethod
    def _function_names(verb, is_remote):
        yield verb
        yield verb + ('_remote' if is_remote else '_local')

    @staticmethod
    def _check_arguments(func, kwargs):
        """
        Check kwargs passed match the signature of the function. This is a slight hack but is required since we can't
        catch argument mismatches without catching all TypeErrors which is worse.
        """
        try:
            inspect.signature(func).bind(action=None, **kwargs)
        except TypeError as e:
            raise BadDataException(*e.args) from e

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
