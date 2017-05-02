import asyncio
import logging

import aiohttp

from em2.comms.push import Pusher
from em2.exceptions import Em2ConnectionError, FailedOutboundAuthentication, PushError
from em2.utils import MSGPACK_CONTENT_TYPE, msg_encode, to_unix_ms

CT_HEADER = {'content-type': MSGPACK_CONTENT_TYPE}

logger = logging.getLogger('em2.push.web')


class WebDNSPusher(Pusher):
    async def startup(self):
        await super().startup()
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def get_node(self, domain):
        logger.info('looking for em2 node for "%s"', domain)
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
                    logger.info('looking for em2 node for "%s"', domain)
                    pass
                else:
                    # TODO query host to find associated node
                    node = host
            if node:
                logger.info('em2 node found %s -> %s', domain, node)
                return node
        logger.info('no em2 node found for %s, falling back', domain)
        return self.FALLBACK

    async def _post(self, domain, path, headers, data):
        logger.info('posting to %s > %s', domain, path)
        token = await self.authenticate(domain)
        headers['em2-auth'] = token
        url = f'{self.settings.COMMS_SCHEMA}://{domain}/{path}'
        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status != 201:
                raise PushError('{}: {}'.format(r.status, await r.read()))

    async def _push_em2(self, nodes, action, data):
        action.item = action.item or ''
        path = f'{action.conv}/{action.component}/{action.verb}/{action.item}'
        headers = {
            'content-type': MSGPACK_CONTENT_TYPE,
            'em2-address': action.address,
            'em2-timestamp': str(to_unix_ms(action.timestamp)),
            'em2-event-id': action.event_id,
        }
        post_data = msg_encode(data)
        cos = [self._post(node, path, headers, post_data) for node in nodes]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    async def _authenticate_direct(self, domain):
        url = f'{self.settings.COMMS_SCHEMA}://{domain}/authenticate'
        # TODO more error checks
        auth_data = self.get_auth_data()
        headers = {f'em2-{k}': str(v) for k, v in auth_data.items()}
        try:
            async with self.session.post(url, headers=headers) as r:
                if r.status != 201:
                    body = await r.text()
                    raise FailedOutboundAuthentication(f'{url} response {r.status} != 201, response:\n{body}')
        except aiohttp.ClientOSError as e:
            # generally "could not resolve host" or "connection refused",
            # the exception is fairly useless at giving specifics # TODO: perhaps changed with aiohttp 2?
            logger.info('ClientOSError: %e, url: %s', e, url)
            raise Em2ConnectionError(f'cannot connect to "{url}"') from e
        key = r.headers['em2-key']
        return key

    async def shutdown(self):
        self.session and await self.session.close()
        await super().close()
