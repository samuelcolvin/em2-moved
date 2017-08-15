"""
Views dedicated to propagation of data between platforms.
"""
import logging

from aiohttp import web
from aiohttp.web_exceptions import HTTPBadRequest, HTTPForbidden, HTTPNotFound

from em2.core import ApplyAction, Components, GetConv, Verbs
from em2.utils import get_domain
from em2.utils.web import View, WebModel, raw_json_response

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

    def required_header(self, name):
        try:
            return self.request.headers[name]
        except KeyError:
            raise HTTPBadRequest(text=f'header "{name}" missing')


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

        key = await self.auth.authenticate_platform(headers.platform, headers.timestamp, headers.signature)
        return web.Response(status=201, headers={'em2-key': key})


class Get(ForeignView):
    async def call(self, request):
        platform = await self.auth.validate_platform_token(self.required_header('em2-auth'))

        prt_address = self.required_header('em2-participant')
        prt_domain = get_domain(prt_address)
        await self.auth.check_domain_platform(prt_domain, platform)

        conv_key = request.match_info['conv']
        logger.info('platform %s getting %.6s', platform, conv_key)
        json_str = await GetConv(self.conn).run(conv_key, prt_address)
        return raw_json_response(json_str)


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

    async def call(self, request):
        platform = await self.auth.validate_platform_token(self.required_header('em2-auth'))
        logger.info('action from %s', platform)

        actor_address = self.required_header('em2-actor')
        address_domain = get_domain(actor_address)

        await self.auth.check_domain_platform(address_domain, platform)

        conv_key = request.match_info['conv']
        component = request.match_info['component']
        verb = request.match_info['verb']
        item = request.match_info['item'] or None
        r = await self.conn.fetchrow(self.find_participant_sql, conv_key, actor_address)
        if not r:
            if await self.conn.fetchval(self.get_conv_sql, conv_key):
                # if the conv already exists this actor is not a participant in it
                raise HTTPForbidden(text=f'"{actor_address}" is not a participant in this conversation')
            else:
                if not (component == Components.PARTICIPANT and verb == Verbs.ADD):
                    raise HTTPNotFound(text='conversation not found')

                new_prt_domain = get_domain(item)
                if not new_prt_domain:
                    raise HTTPBadRequest(text='participant address (item) missing')

                if not await self.pusher.domain_is_local(new_prt_domain):
                    raise HTTPBadRequest(text=f'participant "{item}" not linked to this platform')

                await self.pusher.create_conv(platform, conv_key, item)
                return web.Response(status=204)

        conv_id, actor_id = r

        apply_action = ApplyAction(
            self.conn,
            remote_action=True,
            action_key=self.required_header('em2-action-key'),
            conv=conv_id,
            actor=actor_id,
            timestamp=self.required_header('em2-timestamp'),
            component=component,
            verb=verb,
            item=item,
            parent=self.request.headers.get('em2-parent'),
            body=await request.text(),
            relationship=self.request.headers.get('em2-relationship'),
        )
        await apply_action.run()
        await self.pusher.push(apply_action.action_id, transmit=False)
        return web.Response(status=201)
