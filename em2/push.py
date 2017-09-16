import asyncio
import base64
import logging
from datetime import datetime
from typing import Dict, Set, Tuple

import aiodns
import aiohttp
from aiodns.error import DNSError
from aiohttp import ClientError
from arq import Actor, concurrent, cron
from arq.jobs import DatetimeJob
from async_timeout import timeout
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from . import Settings
from .core import Action, Components, CreateForeignConv, Verbs, gen_random
from .exceptions import Em2ConnectionError, FailedInboundAuthentication, FailedOutboundAuthentication
from .fallback import FallbackHandler
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
        self.fallback: FallbackHandler = None
        self._resolver = None
        kwargs['redis_settings'] = self.settings.redis
        super().__init__(**kwargs)
        logger.debug('initialising pusher %s', self)

    async def startup(self):
        assert not self._concurrency_enabled or self.is_shadow, 'pusher db should only be started in shadow mode'
        self.db = self.settings.db_cls(self.settings, self.loop)

        resolver = self._get_http_resolver()
        connector = aiohttp.TCPConnector(resolver=resolver, verify_ssl=self.settings.COMMS_VERIFY_SSL)
        self.session = aiohttp.ClientSession(loop=self.loop, connector=connector, read_timeout=10, conn_timeout=10)

        self.fallback = self.settings.fallback_cls(settings=self.settings, loop=self.loop, db=self.db)
        await self.db.startup()
        await self.fallback.startup()

    @classmethod
    def _get_http_resolver(cls):
        return aiohttp.DefaultResolver()

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

    prts_sql = """
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
    first_msg_sql = """
    SELECT body
    FROM messages
    WHERE conv = $1
    """

    success_action_sql = """
    INSERT INTO actions_states (action, ref, platform, status)
    VALUES ($1, $2, $3, 'successful')
    """

    @concurrent
    async def push(self, action_id, transmit=True):
        async with self.db.acquire() as conn:
            *args, message_key, prt_address = await conn.fetchrow(self.action_detail_sql, action_id)
            # TODO perhaps need to add other fields required to understand the action
            action = Action(action_id, *args, message_key or prt_address)

            prts = await conn.fetch(self.prts_sql, action.conv_id)  # TODO more info e.g. bcc etc.

            remote_nodes, local_recipients, fallback_addresses = await self.categorise_addresses(*prts)

            logger.info('%s.%s %.6s to %d participants: %d em2 nodes, local %d, fallback %d',
                        action.component or 'conv', action.verb, action.conv_key,
                        len(prts), len(remote_nodes), len(local_recipients), len(fallback_addresses))

            if local_recipients:
                await self.domestic_push(local_recipients, action)

            if transmit:
                if remote_nodes:
                    await self.foreign_push(remote_nodes, action)

                if fallback_addresses:
                    await self.fallback_push(action, prts, conn)
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
        if action.verb == Verbs.PUBLISH:
            path = f'create/{action.conv_key}/'
        else:
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

    async def fallback_push(self, action: Action, prts, conn):
        subject = await conn.fetchval(self.conv_subject_sql, action.conv_id)
        if action.verb == Verbs.PUBLISH:
            # we need the message body to send
            body = await conn.fetchval(self.first_msg_sql, action.conv_id)
        elif action.component == Components.MESSAGE:
            if action.verb == Verbs.ADD:
                body = action.body
            else:
                raise NotImplementedError()
        elif action.component == Components.PARTICIPANT:
            if action.verb == Verbs.ADD:
                body = f'adding {action.item} to the conversation'
            elif action.verb == Verbs.DELETE:
                body = f'removing {action.item} from the conversation'
            else:
                raise NotImplementedError()
        addresses = {r['address'] for r in prts}
        msg_id = await self.fallback.push(action=action, addresses=addresses, conv_subject=subject, body=body)
        await conn.fetchval(self.success_action_sql, action.id, msg_id, None)

    async def _post(self, domain, address, path, universal_headers, data):
        token = await self.authenticate(domain)
        headers = {
            'em2-auth': token,
            'em2-participant': address,
            **universal_headers
        }
        url = f'{self.settings.COMMS_PROTO}://{domain}/{path}'
        logger.info('posting to %s', url)

        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status not in (201, 204):
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
                    remote_nodes[node].add(address)
                else:
                    remote_nodes[node] = {address}
        return remote_nodes, local_recipients, fallback_addresses

    get_action_id_sql = 'SELECT a.id FROM actions AS a WHERE a.conv = $1 AND a.key = $2'

    @concurrent
    async def create_conv(self, domain, conv_key, participant_address, trigger_action_key):
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
            logger.warning('%s request failed: %s, text="%s"', url, e, text)
            return 1

        async with self.db.acquire() as conn:
            creator = CreateForeignConv(conn)
            conv_id = await creator.run(trigger_action_key, data)
            if not conv_id:
                return 1
            action_id = await conn.fetchval(self.get_action_id_sql, conv_id, trigger_action_key)
        await self.push.direct(action_id, transmit=False)
        return 0

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
        url = f'{self.settings.COMMS_PROTO}://{node_domain}/auth/'
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

    @cron(hour=3, minute=0, run_at_startup=True)
    async def setup_check(self, _retry=0, _retry_delay=2):
        """
        Check whether this node has the correct dns settings.
        """
        if not self.settings.run_setup_check:
            return
        http_pass, dns_pass = False, False
        foreign_app_url = f'{self.settings.COMMS_PROTO}://{self.settings.EXTERNAL_DOMAIN}/'
        try:
            async with self.session.get(foreign_app_url) as r:
                if r.status == 200:
                    data = await r.json()
                    if data['domain'] == self.settings.EXTERNAL_DOMAIN:
                        http_pass = True
                    else:
                        logger.warning('setup check: http domain mismatch: "%s" vs. "%s"',
                                       data['domain'], self.settings.EXTERNAL_DOMAIN)
                else:
                    raise aiohttp.ClientError(f'setup check: {foreign_app_url} response {r.status} not 200')
        except (aiohttp.ClientError, ValueError) as e:
            if _retry < 5:
                logger.info('setup check: error checking http, retrying...')
                await asyncio.sleep(_retry_delay)
                return await self.setup_check.direct(_retry=_retry + 1, _retry_delay=_retry_delay)
            logger.warning('setup check: error checking http %s: %s', e.__class__.__name__, e)

        authenticator = self.settings.authenticator_cls(self.settings, loop=self.loop)
        try:
            public_key = await authenticator.get_public_key(self.settings.EXTERNAL_DOMAIN)
            auth_data = dict(self._auth_data())
            signed_message = '{}:{}'.format(self.settings.EXTERNAL_DOMAIN, auth_data['timestamp'])
            if authenticator.valid_signature(signed_message, auth_data['signature'], public_key):
                dns_pass = True
            else:
                logger.warning('setup check: em2key dns value found but signature validation failed')
        except FailedInboundAuthentication as e:
            logger.warning('setup check: error checking dns setup for: %s', e)

        if http_pass and dns_pass:
            logger.info('setup check: passed')
        else:
            logger.warning('setup check: failed, http_pass=%s dns_pass=%s', http_pass, dns_pass)
        return http_pass, dns_pass

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
