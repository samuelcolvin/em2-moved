import datetime
import inspect
import logging

import pytz

from em2.exceptions import BadDataException, BadHash, VerbNotFound
from em2.settings import Settings

from .components import Components, Messages, Participants
from .conversations import Conversations
from .interactions import Action, Retrieval

logger = logging.getLogger('em2.core')


class Controller:
    """
    Top level class for accessing conversations and conversation components.
    """
    def __init__(self, settings: Settings, *, loop=None):
        self.ds = settings.datastore_cls(settings=settings, loop=loop)
        self.pusher = settings.pusher_cls(settings=settings, loop=loop)
        self.timezone_name = settings.TIMEZONE
        self.ref = '{}-{}'.format(settings.LOCAL_DOMAIN, hex(id(self)))
        self.conversations = Conversations(self)
        components = [Messages, Participants]
        self.components = {c.name: c(self) for c in components}
        self.settings = settings

    async def prepare(self):
        await self.ds.prepare()

    async def act(self, a: Action, **kwargs):
        """
        Routes actions to the appropriate component and executes the right verb.
        :param a: action instance
        :param kwargs: extra key word arguments to pass to the method with action
        :return: result of method associated with verb
        """

        if a.is_remote:
            if a.event_id != a.calc_event_id():
                raise BadHash('event_id "{}" incorrect'.format(a.event_id))
            if not isinstance(a.timestamp, datetime.datetime):
                raise BadDataException('remote actions should always have a timestamp')
        else:
            a.timestamp = self.now_tz()

        func = self._get_function(a)
        self._check_arguments(func, 'action', kwargs)
        logger.info('%s action by "%s" %.6s > %s > %s', a.loc_rem, a.address, a.conv or '-', a.component, a.verb)

        async with self.ds.connection() as conn:
            if a.known_conversation:
                a.cds = self.ds.new_conv_ds(a.conv, conn)
                await a.set_participant()
                return await func(a, **kwargs)
            else:
                a.conn = conn
                return await func(a, **kwargs)

    async def retrieve(self, r: Retrieval, **kwargs):
        """
        Routes retrieval to the appropriate component and executes the right verb.
        :param r: retrieval instance
        :param kwargs: extra key word arguments to pass to the method with retrieval
        :return: result of method associated with verb
        """
        func = self._get_function(r)

        self._check_arguments(func, 'retrieval', kwargs)
        logger.info('%s retrieval by "%s" %.6s > %s > %s', r.loc_rem, r.address, r.conv, r.component, r.verb)

        async with self.ds.connection() as conn:
            if r.known_conversation:
                r.cds = self.ds.new_conv_ds(r.conv, conn)
                await r.set_participant()
                return await func(r, **kwargs)
            else:
                r.conn = conn
                return await func(r, **kwargs)

    def _get_function(self, inter):
        component_cls = self._get_component(inter.component)

        for func_name in self._function_names(inter.verb, inter.is_remote):
            func = getattr(component_cls, func_name, None)
            if func:
                return func
        raise VerbNotFound('{} is not an available verb on {}'.format(inter.verb, inter.component))

    def _get_component(self, component_name):
        if component_name == Components.CONVERSATIONS:
            return self.conversations
        else:
            return self.components[component_name]

    @staticmethod
    def _function_names(verb, is_remote):
        yield verb
        yield verb + ('_remote' if is_remote else '_local')

    @staticmethod
    def _check_arguments(func, std_arg_name, kwargs):
        """
        Check kwargs passed match the signature of the function. This is a slight hack but is required since we can't
        catch argument mismatches without catching all TypeErrors which is worse.
        """
        try:
            inspect.signature(func).bind(**{std_arg_name: None}, **kwargs)
        except TypeError as e:
            raise BadDataException('{}: {}'.format(func.__qualname__, e.args[0])) from e

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)

    def now_tz(self):
        return self.timezone.localize(datetime.datetime.now())

    def _subdict(self, data, first_chars):
        return {k[2:]: v for k, v in data.items() if k[0] in first_chars}

    async def event(self, a: Action, **data):
        """
        Record and push updates of conversations and conversation components.

        :param a: Action instance
        :param data: extra information to either be saved (s_*), pushed (p_*) or both (b_*)
        """
        save_data = self._subdict(data, 'sb')
        event_id = a.calc_event_id()
        await a.cds.save_event(event_id, a, **save_data)
        conv_status = await a.get_conv_status()
        if a.is_remote:
            # TODO some way to push events to clients here
            return
        if conv_status == Conversations.Status.DRAFT:
            return
        push_data = self._subdict(data, 'pb')
        await self.pusher.push(a, event_id, push_data)

    async def publish(self, a, **data):
        logger.info('publishing %.6s, author: "%s"', a.conv, a.address)
        event_id = a.calc_event_id()
        await a.cds.save_event(event_id, a)
        # we could change Conversation.remote_add to accept **data and therefore just pass push_data below
        await self.pusher.push(a, event_id, {'data': data})

    def __repr__(self):
        return '<Controller({})>'.format(self.ref)
