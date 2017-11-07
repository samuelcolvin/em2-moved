import asyncio
import base64
import json
import logging
from datetime import datetime
from enum import IntEnum
from typing import Dict, Optional, Set, Tuple, Union

import aiohttp
from aiohttp.hdrs import METH_GET, METH_POST
from aiohttp.web_response import Response
from arq import Actor, concurrent, cron
from arq.jobs import DatetimeJob
from asyncpg.connection import Connection as PGConnection
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from . import Settings
from .core import Action, ActionStatuses, CreateForeignConv, Verbs, gen_random
from .dns import DNSResolver
from .exceptions import Em2ConnectionError, FailedInboundAuthentication
from .fallback import FallbackHandler
from .utils import get_domain
from .utils.encoding import msg_encode, to_unix_ms

logger = logging.getLogger('em2.push')


class ReadMethod(IntEnum):
    text = 1
    json = 2


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
        self.dns = DNSResolver(self.settings, self.loop)
        kwargs['redis_settings'] = self.settings.redis
        super().__init__(**kwargs)
        logger.debug('initialising pusher %s', self)
        self.auth_check_url = settings.auth_server_url + '/check-user-node/'
        self.auth_check_headers = {'Authorization': settings.auth_node_secret}

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
    m.format, m.key, prt_r.address
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
                    await self.foreign_push(remote_nodes, action, conn)

                if fallback_addresses:
                    await self.fallback.push(action, prts, conn)
            # TODO save actions_status

    async def domestic_push(self, recipient_ids: Set[int], action: Action):
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

    async def foreign_push(self, node_lookup: Dict[str, Set[str]], action: Action, conn: PGConnection):
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
            'em2-msg-format': action.msg_format,
        }
        universal_headers = {k: v for k, v in universal_headers.items() if v is not None}
        data = action.body and action.body.encode()
        cos = [
            self._post(node, addresses.pop(), path, universal_headers, data, action, conn)
            for node, addresses in node_lookup.items()
        ]
        # TODO better error checks
        await asyncio.gather(*cos, loop=self.loop)

    success_action_sql = """
    INSERT INTO action_states (action, node, status)
    VALUES ($1, $2, 'successful')
    """

    failed_action_sql = """
    INSERT INTO action_states (action, node, status, errors)
    VALUES ($1, $2, $3, ARRAY[$4::JSONB])
    """

    async def _post(self, node_domain, address, path, universal_headers, data, action: Action, conn):
        # TODO retry on failure and update state on subsequent tries rather than INSERT
        stage = 'auth'
        try:
            token = await self.authenticate(node_domain)
            headers = {
                'em2-auth': token,
                'em2-participant': address,
                **universal_headers
            }
            url = f'{self.settings.COMMS_PROTO}://{node_domain}/{path}'
            logger.info('posting to %s', url)
            stage = 'post'
            await self._request(METH_POST, url, data=data, headers=headers, expected_statuses={201, 204})
        except Em2ConnectionError as exc:
            e = json.dumps({
                'stage': stage,
                'error': str(exc),
                'ts': datetime.utcnow().isoformat(),
            })
            await conn.execute(self.failed_action_sql, action.id, node_domain, ActionStatuses.failed, e)
        else:
            await conn.execute(self.success_action_sql, action.id, node_domain)

    async def get_node(self, address: str) -> str:
        """
        Find the node for a given participant in a conversation.

        :param address: address to find node for
        :return: node's domain or None if em2 is not enabled for this address
        """
        logger.info('looking for em2 node for "%s"', address)
        if await self.check_local(address):
            logger.info('em2 local node found for "%s"', address)
            return self.LOCAL
        domain = get_domain(address)
        async for host in self.dns.mx_hosts(domain):
            if await self.dns.is_em2_node(host):
                try:
                    await self.authenticate(host)
                except Em2ConnectionError:
                    # connection failed domain is probably not em2
                    pass
                else:
                    # TODO query host to find associated node using address
                    logger.info('em2 node found %s -> %s', domain, host)
                    return host
        logger.info('no em2 node found for %s, falling back', domain)
        return self.FALLBACK

    async def categorise_addresses(self, *parts: str) -> Tuple[Dict[str, Set[str]], Set[int], Set[str]]:
        remote_nodes = {}
        local_recipients = set()
        fallback_addresses = set()

        local_cache = {}

        async with await self.get_redis_conn() as redis:
            for recipient_id, address in parts:

                node = local_cache.get(address)
                if not node:
                    key = self.domain_node_prefix + address.encode()
                    node_b = await redis.get(key)
                    if node_b:
                        node = node_b.decode()
                        logger.info('found cached node %s -> %s', address, node)
                    else:
                        node = await self.get_node(address)
                        logger.info('got node for %s -> %s', address, node)
                        await redis.setex(key, self.settings.COMMS_DNS_CACHE_EXPIRY, node.encode())
                    local_cache[address] = node

                if node == self.LOCAL:
                    local_recipients.add(recipient_id)
                elif node == self.FALLBACK:
                    fallback_addresses.add(address)
                elif node in remote_nodes:
                    remote_nodes[node].add(address)
                else:
                    remote_nodes[node] = {address}
        return remote_nodes, local_recipients, fallback_addresses

    @concurrent
    async def create_conv(self, domain, conv_key, participant_address, trigger_action_key):
        logger.info('getting conv %.6s from %s', conv_key, domain)

        url = f'{self.settings.COMMS_PROTO}://{domain}/get/{conv_key}/'
        headers = {
            'em2-auth': await self.authenticate(domain),
            'em2-participant': participant_address,
        }
        try:
            r, data = await self._request(METH_GET, url, headers=headers, read=ReadMethod.json)
        except Em2ConnectionError:
            return 1

        async with self.db.acquire() as conn:
            creator = CreateForeignConv(conn)
            conv_id, action_id = await creator.run(trigger_action_key, data)
            if not conv_id:
                return 1
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
                await asyncio.gather(
                    redis.set(token_key, token),
                    redis.expireat(token_key, expire_token_at),
                )
        logger.info('successfully authenticated with %s', node_domain)
        return token

    async def check_local(self, address: str) -> str:
        _, data = await self._request(
            METH_GET,
            self.auth_check_url,
            json_data={'address': address, 'domain': self.settings.EXTERNAL_DOMAIN},
            headers=self.auth_check_headers,
            retry_delay=0.1,
        )
        return data['local']

    async def _authenticate_request(self, node_domain):
        url = f'{self.settings.COMMS_PROTO}://{node_domain}/auth/'
        headers = {f'em2-{k}': str(v) for k, v in self._auth_data()}
        r, _ = await self._request(METH_POST, url, headers=headers, expected_statuses={201})
        return r.headers['em2-key']

    async def _request(self, method, url, *,
                       data=None,
                       json_data=None,
                       headers=None,
                       read: Optional[ReadMethod] = None,
                       expected_statuses: Set[int]={200},
                       retry_delay=2.0) -> Tuple[Response, Union[str, dict]]:
        exc = response_data = None
        if json_data:
            data = json.dumps(json_data)
            read = read or ReadMethod.json
        for i in range(5):
            try:
                # TODO check timeouts are caught
                async with self.session.request(method, url, data=data, headers=headers, timeout=5) as r:
                    # always read entire response before closing the connection
                    if read == ReadMethod.text or r.status not in expected_statuses:
                        response_data = await r.text()
                    elif read == ReadMethod.json:
                        response_data = await r.json()
            except (aiohttp.ClientError, aiohttp.ClientConnectionError, ValueError) as e:
                exc = f'{e.__class__.__name__}: {e}'
            else:
                if r.status in expected_statuses:
                    logger.debug('%s %s -> %s', method, url, r.status)
                    return r, response_data
                exc = f'bad response: {r.status}'
                if r.status <= 500:
                    # responses greater than 500 might be temporary and should be retried
                    break
            logger.info('%s %s: connection error, retrying...', method, url)
            await asyncio.sleep(retry_delay)
        logger.warning('error on %s to %s, %s', method, url, exc, extra={'data': {
            'method': method,
            'url': url,
            'data': data,
            'headers': headers,
            'response_data': response_data
        }})
        raise Em2ConnectionError(exc)

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

    @cron(hour=3, minute=0, run_at_startup=True)
    async def setup_check(self, _retry_delay=2):
        """
        Check whether this node has the correct dns settings.
        """
        if not self.settings.run_setup_check:
            return
        http_pass, dns_pass = False, False
        foreign_app_url = f'{self.settings.COMMS_PROTO}://{self.settings.EXTERNAL_DOMAIN}/'
        try:
            r, _ = await self._request(METH_GET, foreign_app_url, retry_delay=_retry_delay)
        except Em2ConnectionError:
            pass
        else:
            data = await r.json()
            if data['domain'] == self.settings.EXTERNAL_DOMAIN:
                http_pass = True
            else:
                logger.warning('setup check: http domain mismatch: "%s" vs. "%s"',
                               data['domain'], self.settings.EXTERNAL_DOMAIN)

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

    @staticmethod
    def _now_unix():
        return to_unix_ms(datetime.utcnow())

    def __repr__(self):
        ref = 'shadow' if self.is_shadow else 'frontend'
        return f'<{self.__class__.__name__}:{self.settings.EXTERNAL_DOMAIN}:{ref}>'
