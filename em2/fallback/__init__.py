import logging
from em2 import Settings
from em2.core import Components, Verbs

logger = logging.getLogger('em2.fallback')


class FallbackHandler:
    def __init__(self, settings: Settings, loop=None, **kwargs):
        self.settings = settings
        self.loop = loop

    async def startup(self):
        pass

    async def shutdown(self):
        pass

    def get_from_to_bcc(self, action, participants):
        _from = None
        _to = []
        _bcc = []  # TODO
        for p in participants:
            addr = p['address']
            if addr == action.actor:
                _from = addr
            else:
                _to.append(addr)
        return _from, _to, _bcc

    async def push(self, action, participants, conv_subject):
        e_from, to, bcc = self.get_from_to_bcc(action, participants)
        logger.info('%.6s %s . %s, from: %s, to: (%d) %s', action.conv_key, action.component, action.verb,
                    e_from, len(to) + len(bcc), ', '.join(to))


class SmtpFallbackHandler(FallbackHandler):
    footer_message = (
        "You're participating in the em2 conversation {conv_id:.6}. "
        "Reply to this email to contribute to the conversation.\n"
        "You might consider upgrading to email 2.0 to get a greatly improved email experience."
    )

    plain_footer = '\n\n--\n{}\n'.format(footer_message)
    html_footer = ('\n<p style="font-size:small;color:#666;">&mdash;<br>\n'
                   '{}</p>\n'.format(footer_message.replace('\n', '<br>\n')))

    async def push(self, action, data, participants, conv_subject):
        e_from, to, bcc = self.get_from_to_bcc(action, participants)
        if action.component == Components.CONVERSATIONS and action.verb == Verbs.ADD:
            subject = conv_subject
            body = '\n'.join(m['body'] for m in data[Components.MESSAGES])
        else:
            subject = 'Re: ' + conv_subject
            if action.component == Components.MESSAGES and action.verb == Verbs.ADD:
                body = data['body']
            else:
                # TODO (this is just a bodge)
                import json
                body = json.dumps(data, indent=2)
        msg_id = await self.send_message(
            e_from=e_from,
            to=to,
            bcc=bcc,
            subject=subject,
            plain_body=self.plain_format(body, action.conv),
            html_body=self.html_format(body, action.conv),
        )
        logger.info('message sent conv %.6s, smtp message id %0.6s', action.conv, msg_id)

    async def send_message(self, *, e_from, to, bcc, subject, plain_body, html_body):
        raise NotImplementedError()

    def plain_format(self, body: str, conv_id: str) -> str:
        return body + self.plain_footer.format(conv_id=conv_id)

    def html_format(self, body: str, conv_id: str) -> str:
        # TODO render markdown
        html_body = '\n'.join('<p>{}</p>\n\n'.format(l) for l in body.split('\n'))
        return html_body + self.html_footer.format(conv_id=conv_id)
