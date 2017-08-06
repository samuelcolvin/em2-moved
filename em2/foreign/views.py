"""
Views dedicated to propagation of data between platforms.
"""
import logging

from aiohttp import web
from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden

from em2.core import ApplyAction
from em2.exceptions import FailedInboundAuthentication
from em2.utils.web import View, WebModel

logger = logging.getLogger('em2.foreign.views')


def get_ip(request):
    # TODO switch to use X-Forwarded-For
    peername = request.transport.get_extra_info('peername')
    ip = '-'
    if peername is not None:
        ip, _ = peername
    return ip


class ForeignView(View):
    def __init__(self, request):
        super().__init__(request)
        self.auth = self.app['authenticator']


class Authenticate(ForeignView):
    class Headers(WebModel):
        platform: str
        timestamp: int
        signature: str

        class Config:
            fields = {
                'platform': 'em2-platform',
                'timestamp': 'em2-timestamp',
                'signature': 'em2-signature',
            }

    async def call(self, request):
        logger.info('authentication request from %s', get_ip(request))
        headers = self.Headers(**request.headers)
        logger.info('authentication data: %s', headers)

        try:
            key = await self.auth.authenticate_platform(headers.platform, headers.timestamp, headers.signature)
        except FailedInboundAuthentication as e:
            logger.info('failed inbound authentication: %s', e)
            raise HTTPBadRequest(text=e.args[0] + '\n') from e
        return web.Response(text='ok\n', status=201, headers={'em2-key': key})


class Act(ForeignView):
    find_participant_sql = """
    SELECT c.id, p.id
    FROM conversations AS c
    JOIN participants AS p ON c.id = p.conv
    JOIN recipients AS r ON p.recipient = r.id
    WHERE c.key = $1 AND r.address = $2
    """
    get_conv_sql = """
    SELECT id FROM conversations WHERE key = $1
    """

    def required_header(self, name):
        try:
            return self.request.headers[name]
        except KeyError:
            raise HTTPBadRequest(text=f'header "{name}" missing')

    async def call(self, request):
        platform = await self.auth.validate_platform_token(self.required_header('em2-auth'))
        logger.info('action from %s', platform)

        actor_address = self.required_header('em2-actor')
        _, address_domain = actor_address.split('@', 1)

        await self.auth.check_domain_platform(address_domain, platform)

        conv_key = request.match_info['conv']
        r = await self.conn.fetchrow(self.find_participant_sql, conv_key, actor_address)
        if not r:
            if await self.conn.fetchval(self.get_conv_sql, conv_key):
                # if the conv already exists this actor is not a participant in it
                raise HTTPForbidden(text=f'"{actor_address}" is not a participant in this conversation')
            else:
                # TODO call create_cov
                return web.Response(status=204)

        conv_id, actor_id = r

        apply_action = ApplyAction(
            self.conn,
            create_timestamp=False,
            action_key=self.required_header('em2-action-key'),
            conv=conv_id,
            actor=actor_id,
            timestamp=self.required_header('em2-timestamp'),
            component=request.match_info['component'],
            verb=request.match_info['verb'],
            item=request.match_info['item'] or None,
            parent=self.request.headers.get('em2-parent'),
            body=await request.text(),
            relationship=self.request.headers.get('em2-relationship'),
        )
        await apply_action.run()
        await self.pusher.push(apply_action.action_id, transmit=False)
        return web.Response(status=201)
