import base64
import logging
from typing import Set

from arq import concurrent
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2 import Settings
from em2.utils import now_unix_secs

from .redis import RedisDNSActor

logger = logging.getLogger('em2.push')


class BasePusher:
    """
    Pushers are responsible for distributing data to other platforms and also for prompting the distribution of
    data to addresses which do not support em2, eg. to SMTP addresses.

    To do this Pushers should keep track of the distinct platforms involved in each conversation,
    but also keep a complete list of participants to be included (eg. cc'd in SMTP) in fallback.

    """
    LOCAL = 'L'
    B_LOCAL = LOCAL.encode()
    FALLBACK = 'F'

    def __init__(self, settings: Settings, *, loop=None, fallback=None, **kwargs):
        self.settings = settings
        self.loop = loop
        self.fallback = fallback
        super().__init__(**kwargs)
        logger.info('initialising pusher %s', self)
        self._early_token_expiry = self.settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY
        self.ds = None

    async def ainit(self):
        assert self.ds is None, 'datastore already initialised'
        self.ds = self.settings.datastore_cls(settings=self.settings, loop=self.loop)
        await self.ds.ainit()

    async def push(self, action, event_id, data):
        raise NotImplementedError()

    def get_domain(self, address):
        """
        Parse an address and return its domain.
        """
        return address[address.index('@') + 1:]

    async def get_node(self, domain: str) -> str:
        """
        Find the node for a given participant in a conversation.

        :param domain: domain to find node for
        :return: node's domain or None if em2 is not enabled for this address
        """
        raise NotImplementedError()

    async def get_nodes(self, *addresses: str) -> Set[str]:
        """
        Find a set of em2 enabled nodes/platforms for a list of address.

        :param addresses: participants' addresses
        :return: set of node domains
        """
        nodes = set()
        checked_domains = set()
        for address in addresses:
            d = self.get_domain(address)
            if d not in checked_domains:
                checked_domains.add(d)
                nodes.add(await self.get_node(d))
        return nodes

    def get_auth_data(self):
        timestamp = self._now_unix()
        msg = '{}:{}'.format(self.settings.LOCAL_DOMAIN, timestamp)
        h = SHA256.new(msg.encode())

        key = RSA.importKey(self.settings.PRIVATE_DOMAIN_KEY)
        signer = PKCS1_v1_5.new(key)
        signature = base64.urlsafe_b64encode(signer.sign(h)).decode()
        return {
            'platform': self.settings.LOCAL_DOMAIN,
            'timestamp': timestamp,
            'signature': signature,
        }

    async def authenticate(self, node_domain: str):
        raise NotImplementedError()

    def _now_unix(self):
        return now_unix_secs()

    def __repr__(self):
        return '{}<{}>'.format(self.__class__.__name__, self.settings.LOCAL_DOMAIN)


class NullPusher(BasePusher):  # pragma: no cover
    """
    Pusher with no functionality to connect to other platforms. Used for testing or trial purposes only.
    """
    async def push(self, action, event_id, data):
        pass

    async def get_node(self, domain):
        pass

    async def authenticate(self, node_domain: str):
        pass


class LivePusher(BasePusher, RedisDNSActor):
    # prefix hashes of address domain -> node (platform) domain
    domain_node_prefix = b'dn:'
    # prefix for strings containing auth tokens foreach node
    auth_token_prefix = b'ak:'

    async def ainit(self):
        assert self.is_shadow, 'datastore should only be initialised with the pusher in shadow mode'
        await super().ainit()

    async def get_nodes(self, *addresses: str) -> Set[str]:
        # cache here instead of in get_node so we can use the same redis connection
        nodes = set()
        checked_domains = set()
        async with await self.get_redis_conn() as redis:
            for address in addresses:
                d = self.get_domain(address)
                if d in checked_domains:
                    continue
                checked_domains.add(d)

                key = self.domain_node_prefix + d.encode()
                node_b = await redis.get(key)
                if node_b:
                    node = node_b.decode()
                    logger.info('found cached node: % -> %s', d, node)
                else:
                    node = await self.get_node(d)
                    await redis.setex(key, self.settings.COMMS_DNS_CACHE_EXPIRY, node.encode())
                nodes.add(node)
        return nodes

    async def push(self, action, event_id, data):
        await self._send(action.attrs, event_id, data)

    @concurrent
    async def _send(self, action_attrs, event_id, data):
        async with self.ds.connection() as conn:
            cds = self.ds.new_conv_ds(action_attrs['conv'], conn)

            participants_data = await cds.receiving_participants()
            addresses = [p['address'] for p in participants_data]
            nodes = await self.get_nodes(*addresses)
            remote_em2_nodes = [n for n in nodes if n not in {self.LOCAL, self.FALLBACK}]

            logger.info('%(verb)s %(conv).6s to %(nodes)d nodes', nodes=len(remote_em2_nodes), **action_attrs)
            await self._push_data(remote_em2_nodes, action_attrs, event_id, **data)
            if any(n for n in nodes if n == self.FALLBACK):
                raise NotImplementedError()
            # TODO update event with success or failure

    async def _push_data(self, urls, action_attrs, event_id, **kwargs):
        raise NotImplementedError()

    async def authenticate(self, node_domain: str) -> str:
        logger.info('authenticating with %s', node_domain)
        token_key = self.auth_token_prefix + node_domain.encode()
        async with await self.get_redis_conn() as redis:
            token = await redis.get(token_key)
            if token:
                return token.decode()
            token = await self._authenticate_direct(node_domain)
            _, expires_at, _ = token.split(':', 2)
            expire_token_at = int(expires_at) - self._early_token_expiry
            await self.set_exat(redis, token_key, token, expire_token_at)
        return token

    async def _authenticate_direct(self, node_domain):
        raise NotImplementedError()
