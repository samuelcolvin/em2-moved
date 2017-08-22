import asyncio
import base64
import logging
from datetime import datetime
from typing import Dict, Set, Tuple

import aiodns
import aiohttp
from aiodns.error import DNSError
from aiohttp import ClientError
from arq import Actor, concurrent
from arq.jobs import DatetimeJob
from async_timeout import timeout
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from . import Settings
from .core import Action, CreateForeignConv, gen_random
from .exceptions import Em2ConnectionError, FailedOutboundAuthentication
from .utils import get_domain
from .utils.encoding import msg_encode, to_unix_ms

logger = logging.getLogger('em2.push')


class Pusher(Actor):
    """
    Pushers are responsible for distributing data to other platforms and also for prompting the distribution of
    data to addresses which do not support em2, eg. to SMTP addresses.

    To do this Pushers should keep track of the distinct platforms involved in each conversation,
    but also keep a complete list of participants to be included (eg. cc'd in SMTP) in fallback.
    """
    job_class = DatetimeJob
    LOCAL = 'L'
    B_LOCAL = LOCAL.encode()
    FALLBACK = 'F'

    # prefix for hashes of address domain -> node (platform) domain
    domain_node_prefix = b'dn:'
    # prefix for strings containing auth tokens foreach node
    auth_token_prefix = b'ak:'

    def __init__(self, settings: Settings, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop or asyncio.get_event_loop()
        self._early_token_expiry = self.settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY
        self.db = None
        self.session = None
        self.fallback = None
        self._resolver = None
        kwargs['redis_settings'] = self.settings.redis
        super().__init__(**kwargs)
        logger.info('initialising pusher %s', self)

    async def startup(self):
        assert not self._concurrency_enabled or self.is_shadow, 'pusher db should only be started in shadow mode'
        self.db = self.settings.db_cls(self.settings, self.loop)

        resolver = self._get_http_resolver()
        connector = aiohttp.TCPConnector(resolver=resolver)
        self.session = aiohttp.ClientSession(loop=self.loop, connector=connector)

        self.fallback = self.settings.fallback_cls(self.settings, self.loop)
        await self.db.startup()
        await self.fallback.startup()

    @classmethod
    def _get_http_resolver(cls):
        return aiohttp.AsyncResolver()

    async def shutdown(self):
        if self.db:
            await self.db.close()
            await self.fallback.shutdown()
            await self.session.close()

    # see core.Action for order of returned values
    action_detail_sql = """
    SELECT a.key, c.key, c.id, a.verb, a.component, actor_r.address, a.timestamp, parent.key, a.body, m.relationship,
    m.key, prt_r.address
    FROM actions AS a
    JOIN conversations AS c ON a.conv = c.id

    JOIN recipients AS actor_r ON a.actor = actor_r.id

    LEFT JOIN actions AS parent ON a.parent = parent.id

    LEFT JOIN messages AS m ON a.message = m.id

    LEFT JOIN recipients AS prt_r ON a.recipient = prt_r.id

    WHERE a.id = $1
    """

    parts_sql = """
    SELECT r.id, r.address
    FROM participants AS p
    JOIN recipients AS r ON p.recipient = r.id
    WHERE p.conv = $1
    """

    conv_subject_sql = """
    SELECT subject
    FROM conversations
    WHERE id = $1
    """

    @concurrent
    async def push(self, action_id, transmit=True):
        async with self.db.acquire() as conn:
            *args, message_key, prt_address = await conn.fetchrow(self.action_detail_sql, action_id)
            # TODO perhaps need to add other fields required to understand the action
            action = Action(*args, message_key or prt_address)

            parts = await conn.fetch(self.parts_sql, action.conv_id)  # TODO more info e.g. bcc etc.

            remote_nodes, local_recipients, fallback_addresses = await self.categorise_addresses(*parts)

            logger.info('%s.%s %.6s to %d participants: %d em2 nodes, local %d, fallback %d',
                        action.component, action.verb, action.conv_key,
                        len(parts), len(remote_nodes), len(local_recipients), len(fallback_addresses))

            if local_recipients:
                await self.domestic_push(local_recipients, action)

            if transmit:
                if remote_nodes:
                    await self.foreign_push(remote_nodes, action)

                if fallback_addresses:
                    subject = await conn.fetch(self.conv_subject_sql, action.conv_id)
                    await self.fallback.push(action, parts, subject)
            # TODO save actions_status

    async def domestic_push(self, recipient_ids, action: Action):
        async with await self.get_redis_conn() as redis:
            recipient_ids_key = gen_random('rid')
            await asyncio.gather(
                redis.sadd(recipient_ids_key, *recipient_ids),
                redis.expire(recipient_ids_key, 60),
            )
            action_dict = action._asdict()
            action_dict.pop('conv_id')
            frontends = await redis.keys(self.settings.FRONTEND_RECIPIENTS_BASE.format('*'), encoding='utf8')
            logger.info('%s.%s %.6s front ends: running: %s', action.component, action.verb, action.conv_key, frontends)
            for frontend in frontends:
                matching_recipient_ids = await redis.sinter(recipient_ids_key, frontend)
                _, name = frontend.rsplit(':', 1)
                if not matching_recipient_ids:
                    logger.info('%s.%s %.6s frontend %s: no matching recipients',
                                action.component, action.verb, action.conv_key, name)
                    continue
                logger.info('%s.%s %.6s frontend %s: %d matching recipients, pushing job',
                            action.component, action.verb, action.conv_key, name, len(matching_recipient_ids))
                job_name = self.settings.FRONTEND_JOBS_BASE.format(name)
                job_data = {
                    'recipients': [int(rid) for rid in matching_recipient_ids],
                    'action': action_dict,
                }
                await redis.rpush(job_name, msg_encode(job_data))

    async def foreign_push(self, node_lookup, action: Action):
        """
        Push action to participants on remote nodes.
        """
        item = action.item or ''
        path = f'{action.conv_key}/{action.component}/{action.verb}/{item}'
        universal_headers = {
            'content-type': 'application/em2',
            'em2-actor': action.actor,
            'em2-timestamp': str(to_unix_ms(action.timestamp)),
            'em2-action-key': action.action_key,
            'em2-parent': action.parent,
            'em2-relationship': action.relationship,
        }
        universal_headers = {k: v for k, v in universal_headers.items() if v is not None}
        data = action.body and action.body.encode()
        cos = [
            self._post(node, addresses.pop(), path, universal_headers, data)
            for node, addresses in node_lookup.items()
        ]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    async def _post(self, domain, address, path, universal_headers, data):
        logger.info('posting to %s > %s', domain, path)
        token = await self.authenticate(domain)
        headers = {
            'em2-auth': token,
            'em2-participant': address,
            **universal_headers
        }
        url = f'{self.settings.COMMS_PROTO}://{domain}/{path}'

        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status != 201:
                text = await r.text()
                logger.warning('%s POST failed %d: %s', url, r.status, text)

    async def get_node(self, domain: str) -> str:
        """
        Find the node for a given participant in a conversation.

        :param domain: domain to find node for
        :return: node's domain or None if em2 is not enabled for this address
        """
        logger.info('looking for em2 node for "%s"', domain)
        if self.settings.DEBUG and domain == 'localhost.example.com':
            # special case for testing
            return self.LOCAL
        async for host in self.mx_hosts(domain):
            node = None
            if host == self.settings.EXTERNAL_DOMAIN:
                node = self.LOCAL
            elif await self._is_em2_node(host):
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

    async def _is_em2_node(self, host):
        # see if any of the hosts TXT records start with with the prefix for em2 public keys
        dns_results = await self.dns_query(host, 'TXT')
        return any(r.text.decode().startswith('v=em2key') for r in dns_results)

    async def categorise_addresses(self, *parts: str) -> Tuple[Dict[str, Set[str]], Set[str], Set[str]]:
        remote_nodes = {}
        local_recipients = set()
        fallback_addresses = set()

        local_cache = {}

        async with await self.get_redis_conn() as redis:
            for recipient_id, address in parts:
                d = get_domain(address)

                node = local_cache.get(d)
                if not node:
                    key = self.domain_node_prefix + d.encode()
                    node_b = await redis.get(key)
                    if node_b:
                        node = node_b.decode()
                        logger.info('found cached node %s -> %s', d, node)
                    else:
                        node = await self.get_node(d)
                        logger.info('got node for %s -> %s', d, node)
                        await redis.setex(key, self.settings.COMMS_DNS_CACHE_EXPIRY, node.encode())
                    local_cache[d] = node

                if node == self.LOCAL:
                    local_recipients.add(recipient_id)
                elif node == self.FALLBACK:
                    fallback_addresses.add(address)
                elif node in remote_nodes:
                    remote_nodes[node].add(d)
                else:
                    remote_nodes[node] = {d}
        return remote_nodes, local_recipients, fallback_addresses

    @concurrent
    async def create_conv(self, domain, conv_key, participant_address):
        logger.info('getting conv %.6s from %s', conv_key, domain)

        url = f'{self.settings.COMMS_PROTO}://{domain}/get/{conv_key}/'
        headers = {
            'em2-auth': await self.authenticate(domain),
            'em2-participant': participant_address,
        }
        text = None
        try:
            async with self.session.get(url, headers=headers) as r:
                text = await r.text()
                if r.status != 200:
                    raise ClientError(f'status {r.status} not 200')
                data = await r.json()
        except (ValueError, ClientError) as e:
            return logger.warning('%s request failed: %s, text="%s"', url, e, text)

        async with self.db.acquire() as conn:
            creator = CreateForeignConv(conn)
            await creator.run(data)

    async def authenticate(self, node_domain: str) -> str:
        logger.debug('authenticating with %s', node_domain)
        token_key = self.auth_token_prefix + node_domain.encode()
        async with await self.get_redis_conn() as redis:
            token = await redis.get(token_key)
            if token:
                token = token.decode()
            else:
                token = await self._authenticate_request(node_domain)
                _, expires_at, _ = token.split(':', 2)
                expire_token_at = int(expires_at) - self._early_token_expiry
                await self.set_exat(redis, token_key, token, expire_token_at)
        logger.info('successfully authenticated with %s', node_domain)
        return token

    async def _authenticate_request(self, node_domain):
        url = f'{self.settings.COMMS_PROTO}://{node_domain}/authenticate'
        # TODO more error checks
        headers = {f'em2-{k}': str(v) for k, v in self._auth_data()}
        try:
            async with self.session.post(url, headers=headers) as r:
                if r.status != 201:
                    body = await r.text()
                    raise FailedOutboundAuthentication(f'{url} response {r.status} != 201, response:\n{body}')
        except aiohttp.ClientError as e:
            # TODO log error rather than raising
            logger.info('ClientOSError: %e, url: %s', e, url)
            raise Em2ConnectionError(f'cannot connect to "{url}"') from e
        key = r.headers['em2-key']
        return key

    def _auth_data(self):
        yield 'platform', self.settings.EXTERNAL_DOMAIN

        timestamp = self._now_unix()
        yield 'timestamp', timestamp

        msg = '{}:{}'.format(self.settings.EXTERNAL_DOMAIN, timestamp)
        h = SHA256.new(msg.encode())

        key = RSA.importKey(self.settings.private_domain_key)
        signer = PKCS1_v1_5.new(key)
        signature = base64.urlsafe_b64encode(signer.sign(h)).decode()
        yield 'signature', signature

    async def domain_is_local(self, domain: str) -> bool:
        # TODO results should be cached
        async for host in self.mx_hosts(domain):
            if host == self.settings.EXTERNAL_DOMAIN:
                return True
        return False

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=self.settings.COMMS_DNS_IPS)
        return self._resolver

    async def mx_hosts(self, host):
        results = await self.dns_query(host, 'MX')
        results = [(r.priority, r.host) for r in results]
        results.sort()
        for _, host in results:
            yield host

    async def dns_query(self, host, qtype):
        try:
            with timeout(5, loop=self.loop):
                return await self.resolver.query(host, qtype)
        except (DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.warning('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []

    async def set_exat(self, redis, key: bytes, value: str, expires_at: int):
        await asyncio.gather(
            redis.set(key, value),
            redis.expireat(key, expires_at),
        )

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return bool(await redis.exists(platform_token.encode()))

    @staticmethod
    def _now_unix():
        return to_unix_ms(datetime.utcnow())

    def __repr__(self):
        ref = 'shadow' if self.is_shadow else 'frontend'
        return f'<{self.__class__.__name__}:{self.settings.EXTERNAL_DOMAIN}:{ref}>'
