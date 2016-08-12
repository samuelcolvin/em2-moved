import asyncio

import aiohttp
from em2.comms import encoding

from em2.comms.push import AsyncRedisPusher
from em2.exceptions import Em2ConnectionError, FailedOutboundAuthentication, PushError

JSON_HEADER = {'content-type': encoding.MSGPACK_CONTENT_TYPE}


class HttpDNSPusher(AsyncRedisPusher):  # TODO: https
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if not self._session:
            self._session = aiohttp.ClientSession(loop=self.loop)
        return self._session

    async def get_node(self, conv, domain, *addresses):
        cache_key = 'nd:{}:{}'.format(conv, domain).encode()
        async with await self.get_redis_conn() as redis:
            node = await redis.get(cache_key)
            if node:
                return node
            results = await self.resolver.query(domain, 'MX')
            results = [(r.priority, r.host) for r in results]
            results.sort()
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
                    await redis.setex(cache_key, self.settings.COMMS_DOMAIN_CACHE_TIMEOUT, host.encode())
                    return node
        # TODO SMTP fallback
        raise NotImplementedError()

    async def post(self, domain, path, data):
        token = await self.authenticate(domain)
        headers = dict(Authorization=token, **JSON_HEADER)
        url = domain + path
        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status != 201:
                raise PushError('{}: {}'.format(r.status, await r.read()))

    async def _push_data(self, domains, action_attrs, event_id, **kwargs):
        action_attrs['item'] = action_attrs['item'] or ''
        path = '/{conv}/{component}/{verb}/{item}'.format(**action_attrs)
        post_data = {
            'address': action_attrs['address'],
            'timestamp': action_attrs['timestamp'],
            'event_id': event_id,
            'kwargs': kwargs,
        }
        post_data = encoding.encode(post_data)
        cos = [self.post(domain, path, post_data) for domain in domains]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    async def _authenticate_direct(self, domain, data):
        url = domain + '/authenticate'
        if not url.startswith('em2.'):
            url = 'em2.' + url
        # TODO more error checks
        try:
            async with self.session.post(url, data=encoding.encode(data), headers=JSON_HEADER) as r:
                body = await r.read()
        except aiohttp.ClientOSError as e:
            # generally "could not resolve host" or "connection refused",
            # the exception is fairly useless at giving specifics
            raise ConnectionError('conn count connect to "{}"'.format(url)) from e
        else:
            if r.status != 201:
                raise FailedOutboundAuthentication('{} response {} != 201, response: {}'.format(url, r.status, body))
        data = encoding.decode(body)
        return data['key']

    async def close(self):
        if self._session:
            await self._session.close()
        await super().close()
