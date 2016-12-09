import asyncio
import logging

import aiohttp

from em2.comms import encoding
from em2.comms.push import Pusher
from em2.exceptions import Em2ConnectionError, FailedOutboundAuthentication, PushError

JSON_HEADER = {'content-type': encoding.MSGPACK_CONTENT_TYPE}

logger = logging.getLogger('em2.push.http')


class HttpDNSPusher(Pusher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if not self._session:
            logger.info('creating http session')
            self._session = aiohttp.ClientSession(loop=self.loop)
        return self._session

    async def get_node(self, domain):
        results = await self.mx_query(domain)
        for _, host in results:
            node = None
            if host == self.settings.LOCAL_DOMAIN:
                node = self.LOCAL
            elif host.startswith('em2.'):
                try:
                    await self.authenticate(host)
                except Em2ConnectionError:
                    # connection failed domain is probably not em2
                    pass
                else:
                    # TODO query host to find associated node
                    node = host
            if node:
                logger.info('em2 node found %s -> %s', domain, node)
                return node
        logger.info('no em2 node found for %s, falling back', domain)
        return self.FALLBACK

    async def _post(self, domain, path, data):
        logger.info('posting to %s > %s', domain, path)
        token = await self.authenticate(domain)
        headers = dict(Authorization=token, **JSON_HEADER)
        url = 'https://{}/{}'.format(domain, path)
        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status != 201:
                raise PushError('{}: {}'.format(r.status, await r.read()))

    async def _push_em2(self, nodes, action, data):
        action.item = action.item or ''
        path = '{a.conv}/{a.component}/{a.verb}/{a.item}'.format(a=action)
        post_data = {
            'address': action.address,
            'timestamp': action.timestamp,
            'event_id': action.event_id,
            'kwargs': data,
        }
        post_data = encoding.encode(post_data)
        cos = [self._post(node, path, post_data) for node in nodes]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    async def _authenticate_direct(self, domain):
        url = 'https://{}/authenticate'.format(domain)
        # TODO more error checks
        auth_data = self.get_auth_data()
        try:
            async with self.session.post(url, data=encoding.encode(auth_data), headers=JSON_HEADER) as r:
                body = await r.read()
        except aiohttp.ClientOSError as e:
            # generally "could not resolve host" or "connection refused",
            # the exception is fairly useless at giving specifics
            raise Em2ConnectionError('cannot connect to "{}"'.format(url)) from e
        else:
            if r.status != 201:
                raise FailedOutboundAuthentication('{} response {} != 201, response: {}'.format(url, r.status, body))
        data = encoding.decode(body)
        return data['key']

    async def close(self):
        if self._session:
            logger.warning('closing http sessoin')
            await self._session.close()
        await super().close()
