import asyncio
import base64
import logging
from datetime import datetime
from typing import Set

import aiodns
import aiohttp
from aiodns.error import DNSError
from arq import Actor, concurrent
from arq.jobs import DatetimeJob
from async_timeout import timeout
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2 import Settings
from em2.core import Action
from em2.exceptions import Em2ConnectionError, FailedOutboundAuthentication, PushError
from em2.utils.encoding import to_unix_ms

logger = logging.getLogger('em2.push')


def _get_domain(address):
    """
    Parse an address and return its domain.
    """
    return address[address.index('@') + 1:]


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
        self.loop = loop
        logger.info('initialising pusher %s', self)
        self._early_token_expiry = self.settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY
        self.db = None
        self.session = None
        self.fallback = None
        self._resolver = None
        super().__init__(**kwargs)

    async def startup(self):
        assert not self._concurrency_enabled or self.is_shadow, 'pusher db should only be started in shadow mode'
        self.db = self.settings.db_cls(self.settings, self.loop)
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.fallback = self.settings.fallback_cls(self.settings, self.loop)
        await self.db.startup()
        await self.fallback.startup()

    async def shutdown(self):
        if self.db:
            await self.db.shutdown()
            await self.fallback.shutdown()
            await self.session.close()

    part_addresses_sql = """
    SELECT r.address
    FROM participants AS p
    JOIN recipients AS r ON p.recipient = r.id
    WHERE p.conv = $1 AND p.active = TRUE
    """

    conv_subject_sql = """
    SELECT subject
    FROM conversations
    WHERE id = $1
    """

    @concurrent
    async def propagate(self, *,
                        action_id,
                        action_key,
                        conv_key,
                        conv_id,
                        component,
                        verb,
                        actor,
                        timestamp,
                        parent=None,
                        relationship=None,
                        item=None,
                        body=None):
        action = Action(
            action_id=action_id,
            action_key=action_key,
            conv_id=conv_id,
            conv_key=conv_key,
            component=component,
            verb=verb,
            actor=actor,
            timestamp=timestamp,
            parent=parent,
            relationship=relationship,
            body=body,
            item=item,
        )
        async with self.db.acquire() as conn:
            participants = await conn.fetch(self.part_addresses_sql, conv_id)  # TODO more info e.g. bcc etc.
            addresses = [p[0] for p in participants]
            # TODO use self.propagate instance to propagate action to all domestic users.
            nodes = await self.get_nodes(*addresses)
            print('nodes:', nodes)
            remote_em2_nodes = {n for n in nodes if n not in {self.LOCAL, self.FALLBACK}}
            logger.info('%s.%s %.6s to %d participants on %d nodes, of which em2 %d', component, verb, conv_key,
                        len(participants), len(nodes), len(remote_em2_nodes))
            if remote_em2_nodes:
                await self.push(remote_em2_nodes, action)

            if any(n for n in nodes if n == self.FALLBACK):
                logger.info('%s %.6s fallback required', verb, conv_key)
                # some actions eg. publish already include subject
                subject = await conn.fetch(self.conv_subject_sql, conv_id)
                await self.fallback.push(action, participants, subject)
            # TODO save actions_status

    async def push(self, nodes, action: Action):
        item = action.item or ''
        path = f'{action.conv_key}/{action.component}/{action.verb}/{item}'
        headers = {
            'content-type': 'text/plain',
            'em2-actor': action.actor,
            'em2-timestamp': action.timestamp,
            'em2-action-key': action.action_key,
            'em2-parent': action.parent,
            'em2-relationship': action.relationship,
        }
        cos = [self._post(node, path, headers, action.body.encode()) for node in nodes]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    async def _post(self, domain, path, headers, data):
        logger.info('posting to %s > %s', domain, path)
        token = await self.authenticate(domain)
        headers['em2-auth'] = token
        url = f'{self.settings.COMMS_SCHEMA}://{domain}/{path}'
        # TODO semaphore to limit maximum connection count
        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status != 201:
                # FIXME shouldn't raise an error here as we're inside a task, should just log
                raise PushError('{}: {}'.format(r.status, await r.read()))

    async def get_node(self, domain: str) -> str:
        """
        Find the node for a given participant in a conversation.

        :param domain: domain to find node for
        :return: node's domain or None if em2 is not enabled for this address
        """
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
                    pass
                else:
                    # TODO query host to find associated node
                    node = host
            if node:
                logger.info('em2 node found %s -> %s', domain, node)
                return node
        logger.info('no em2 node found for %s, falling back', domain)
        return self.FALLBACK

    async def get_nodes(self, *addresses: str) -> Set[str]:
        # cache here instead of in get_node so we can use the same redis connection
        nodes = set()
        checked_domains = set()
        async with await self.get_redis_conn() as redis:
            for address in addresses:
                d = _get_domain(address)
                if d in checked_domains:
                    continue
                checked_domains.add(d)

                key = self.domain_node_prefix + d.encode()
                node_b = await redis.get(key)
                if node_b:
                    node = node_b.decode()
                    logger.info('found cached node %s -> %s', d, node)
                else:
                    node = await self.get_node(d)
                    logger.info('got node for %s -> %s', d, node)
                    await redis.setex(key, self.settings.COMMS_DNS_CACHE_EXPIRY, node.encode())
                nodes.add(node)
        return nodes

    def auth_data(self):
        yield 'platform', self.settings.LOCAL_DOMAIN

        timestamp = self._now_unix()
        yield 'timestamp', timestamp

        msg = '{}:{}'.format(self.settings.LOCAL_DOMAIN, timestamp)
        h = SHA256.new(msg.encode())

        key = RSA.importKey(self.settings.private_domain_key)
        signer = PKCS1_v1_5.new(key)
        signature = base64.urlsafe_b64encode(signer.sign(h)).decode()
        yield 'signature', signature

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
        url = f'{self.settings.COMMS_SCHEMA}://{node_domain}/authenticate'
        # TODO more error checks
        headers = {f'em2-{k}': str(v) for k, v in self.auth_data()}
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

    @property
    def resolver(self):
        if self._resolver is None:
            nameservers = [self.settings.COMMS_DNS_IP] if self.settings.COMMS_DNS_IP else None
            self._resolver = aiodns.DNSResolver(loop=self.loop, nameservers=nameservers)
        return self._resolver

    async def mx_query(self, host):
        results = await self.dns_query(host, 'MX')
        results = [(r.priority, r.host) for r in results]
        results.sort()
        return results

    async def dns_query(self, host, qtype):
        try:
            with timeout(5, loop=self.loop):
                return await self.resolver.query(host, qtype)
        except (DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.warning('%s query error on %s, %s %s', qtype, host, e.__class__.__name__, e)
            return []

    async def set_exat(self, redis, key: bytes, value: str, expires_at: int):
        pipe = redis.pipeline()
        pipe.set(key, value)
        pipe.expireat(key, expires_at)
        await pipe.execute()

    async def key_exists(self, platform_token: str):
        async with await self.get_redis_conn() as redis:
            return bool(await redis.exists(platform_token.encode()))

    @staticmethod
    def _now_unix():
        return to_unix_ms(datetime.utcnow())

    def __repr__(self):
        return '{}<{}>'.format(self.__class__.__name__, self.settings.LOCAL_DOMAIN)
