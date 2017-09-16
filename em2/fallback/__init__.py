import email
import logging
import quopri
from email.message import Message
from textwrap import indent
from typing import List

from bs4 import BeautifulSoup

from em2 import Settings
from em2.core import Action
from em2.utils.markdown import markdown

logger = logging.getLogger('em2.fallback')


class FallbackHandler:
    def __init__(self, settings: Settings, loop=None, db=None):
        self.settings = settings
        self.loop = loop
        self.html_template = settings.smtp_html_template.read_text()
        self.db = db

    async def startup(self):
        pass

    async def shutdown(self):
        pass

    def get_from_to_bcc(self, action, addresses):
        _from = None
        _to = []
        _bcc = []  # TODO
        for addr in addresses:
            if addr == action.actor:
                _from = addr
            else:
                _to.append(addr)
        return _from, _to, _bcc

    async def push(self, *, action: Action, addresses, conv_subject, body):
        e_from, to, bcc = self.get_from_to_bcc(action, addresses)
        msg_id = await self.send_message(
            e_from=e_from,
            to=to,
            bcc=bcc,
            subject=conv_subject,
            body=body,
            action=action,
        )
        logger.info('message sent conv %.6s, smtp message id %0.12s...', action.conv_key, msg_id)
        return msg_id

    async def send_message(self, *, e_from: str, to: List[str], bcc: List[str], subject: str, body: str,
                           action: Action):
        raise NotImplementedError()

    def plain_format(self, body: str, conv_id: str) -> str:
        return body + '\n\n--\nconv: {:.6}'.format(conv_id)

    def html_format(self, body: str, conv_id: str) -> str:
        body_html = markdown(body)
        return self.html_template % dict(body_html=body_html, conv_id=conv_id)

    async def process_webhook(self, request):
        pass

    async def process_smtp_message(self, smtp_content: str):
        # TODO deal with non multipart
        msg: Message = email.message_from_string(smtp_content)
        # debug(dict(msg))
        # find which conversation this relates to
        in_reply_to = msg['In-Reply-To']
        async with self.db.acquire() as conn:
            # TODO search action states for in_reply_to, if not found, look in other headers like references (outlook)
            # TODO, need to remove names etc.
            recipients = msg['To'].split(',')
            assert in_reply_to
            assert conn
            assert recipients

            # text/html is generally the best representation of the email
            body = None
            is_html = True
            for m in msg.walk():
                ct = m['Content-Type']
                if 'text' in ct:
                    body = m.get_payload()
                if 'text/html' in ct:
                    if m['Content-Transfer-Encoding'] == 'quoted-printable':
                        body = quopri.decodestring(body).decode()
                    is_html = True
                    break
            if not body:
                logger.error('Unable to body in email', extra={'raw-smtp': smtp_content})

            if is_html:
                soup = BeautifulSoup(body, 'html.parser')

                # if this is a gmail email, remove the extra content
                soup.select_one('div.gmail_extra') and soup.select_one('div.gmail_extra').decompose()

                body = soup.prettify().strip('\n')
                print(body)  # TODO


class LogFallbackHandler(FallbackHandler):
    async def send_message(self, *, e_from: str, to: List[str], bcc: List[str], subject: str, body: str,
                           action: Action):
        plain_body = self.plain_format(body, action.conv_key)
        logger.info('%s > %s, subject: "%s"\n%s', e_from, to, subject, indent(plain_body, '  '))
