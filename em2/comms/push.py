import base64
import logging

from arq import concurrent
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from em2.utils import BaseServiceCls, now_unix_secs

from .redis import RedisDNSActor

logger = logging.getLogger('em2.push')


class BasePusher(BaseServiceCls):
    """
    Pushers are responsible for distributing data to other platforms and also for prompting the distribution of
    data to addresses which do not support em2, eg. to SMTP addresses.

    To do this Pushers should keep track of the distinct platforms involved in each conversation,
    but also keep a complete list of participants to be included (eg. cc'd in SMTP) in fallback.

    """
    # TODO: pushers need a way of getting data about conversations eg. if the cache is wiped.
    LOCAL = 'L'
    B_LOCAL = LOCAL.encode()

    def __init__(self, settings, *, fallback=None, loop=None, **kwargs):
        self.fallback = fallback
        super().__init__(settings, loop=loop, **kwargs)
        logger.info('initialising pusher %s', self)
        self._early_token_expiry = self.settings.COMMS_PUSH_TOKEN_EARLY_EXPIRY

    async def add_participant(self, conv: str, participant: str):
        """
        Modify internal reference to platforms and participants when a new participant is added to the conversation.
        Participant's platform may or may not be already included in the conversation.

        :param conv: id of conversation
        :param participant: address of participant added
        """
        # TODO deal with "hidden" (eg. bcc) participants, and also participants' names eg. for SMTP "to"
        raise NotImplementedError()

    async def add_many_participants(self, conv: str, *participants: str):
        """
        Modify internal reference to platforms and participants adding multiple participants.

        :param conv: id of conversation
        :param participants: participants of participants added
        """
        raise NotImplementedError()

    async def remove_domain(self, conv, domain):
        raise NotImplementedError()

    async def push(self, action, event_id, data):
        raise NotImplementedError()

    async def publish(self, action, event_id, data):
        raise NotImplementedError()

    def get_domain(self, address):
        """
        Parse an address and return its domain.
        """
        return address[address.index('@') + 1:]

    async def get_node(self, conv: str, domain: str, address: str):
        """
        Find the node for a given participant in a conversation.

        :param conv: conversation id
        :param domain: domain to
        :param address: participant's address
        :return:
        """
        raise NotImplementedError()

    async def get_nodes(self, conv, *addresses):
        domain_nodes = {}
        for address in addresses:
            d = self.get_domain(address)
            if d not in domain_nodes:
                domain_nodes[d] = await self.get_node(conv, d, address)
        return domain_nodes

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
    async def add_participant(self, conv, participant):
        pass

    async def add_many_participants(self, conv, *participants):
        pass

    async def remove_domain(self, conv, domain):
        pass

    async def push(self, action, event_id, data):
        pass

    async def publish(self, action, event_id, data):
        pass

    async def get_node(self, conv, domain, *addresses):
        pass


class livePusher(BasePusher, RedisDNSActor):
    # prefix hashes of address domain -> node (platform) domain for each conversation
    conv_domain_node_prefix = b'pc:'
    # prefix for strings containing auth tokens foreach node
    auth_token_prefix = b'ak:'
    # for fallback, prefix for hashes of address -> info (eg. hidden, name) for each conversation
    conv_fallback_prefix = b'fa:'

    @concurrent
    async def add_participant(self, conv, participant):
        domain = self.get_domain(participant)
        node_hash_key = self.conv_domain_node_prefix + conv.encode()
        fallback_hash_key = self.conv_fallback_prefix + conv.encode()
        b_domain = domain.encode()
        async with await self.get_redis_conn() as redis:
            if not await redis.hexists(node_hash_key, b_domain):
                node = await self.get_node(conv, domain, participant)
                await redis.hset(node_hash_key, b_domain, node)
            await redis.hset(fallback_hash_key, participant.encode(), b'TODO')

    @concurrent
    async def add_many_participants(self, conv, *participants):
        node_hash_key = self.conv_domain_node_prefix + conv.encode()
        fallback_hash_key = self.conv_fallback_prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            domain_nodes = await self.get_nodes(conv, *participants)
            await redis.hmset_dict(node_hash_key, domain_nodes)
            participant_dict = {p.encode(): b'void' for p in participants}
            await redis.hmset_dict(fallback_hash_key, participant_dict)
        return domain_nodes, participant_dict

    @concurrent
    async def remove_domain(self, conv, domain):
        hash_key = self.conv_domain_node_prefix + conv.encode()
        async with await self.get_redis_conn() as redis:
            await redis.hdel(hash_key, domain)

    async def publish(self, action, event_id, data):
        await self._publish_concurrent(action.attrs, event_id, data)

    @concurrent
    async def _publish_concurrent(self, action_attrs, event_id, data):
        from em2.core import Components
        addresses = [p[0] for p in data[Components.PARTICIPANTS]]
        domain_nodes, participants = await self.add_many_participants__direct(action_attrs['conv'], *addresses)
        node_urls = domain_nodes.values()
        remote_urls = [u for u in node_urls if u != self.LOCAL]
        logger.info('publishing %.6s to %d urls', action_attrs['conv'], len(remote_urls))
        await self._push_data(remote_urls, action_attrs, event_id, data=data)

    async def push(self, action, event_id, data):
        await self._push_concurrent(action.attrs, event_id, data)

    @concurrent
    async def _push_concurrent(self, action_attrs, event_id, data):
        print(action_attrs)
        async with await self.get_redis_conn() as redis:
            domain_nodes = await redis.hgetall(self.conv_domain_node_prefix + action_attrs['conv'].encode())
        node_domains = [u.decode() for u in domain_nodes.values() if u != self.B_LOCAL]
        logger.info('pushing %.6s to %d urls', action_attrs['conv'], len(node_domains))
        await self._push_data(node_domains, action_attrs, event_id, **data)

    async def _push_data(self, urls, action_attrs, event_id, **kwargs):
        raise NotImplementedError

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
