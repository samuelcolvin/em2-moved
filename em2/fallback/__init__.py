import email
import logging
import quopri
from email.message import Message
from textwrap import indent
from typing import List

from aiohttp.web_exceptions import HTTPForbidden
from bs4 import BeautifulSoup

from em2 import Settings
from em2.core import Action, ApplyAction, Components, Verbs, Relationships, create_missing_recipients, gen_random, \
    CreateForeignConv, generate_conv_key
from em2.utils import to_utc_naive
from em2.utils.markdown import markdown

logger = logging.getLogger('em2.fallback')


def get_smtp_body(msg: Message, smtp_content):
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
        gmail_extra = soup.select_one('div.gmail_extra') or soup.select_one('div.gmail_signature')
        if gmail_extra:
            gmail_extra.decompose()

        body = soup.prettify().strip('\n')
    return body


class FallbackHandler:
    def __init__(self, settings: Settings, loop, db=None, pusher=None):
        self.settings = settings
        self.loop = loop
        self.html_template = settings.smtp_html_template.read_text()
        self.db = db
        self.pusher = pusher

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

    find_from_refs_sql = """
    SELECT c.id, a.key, a.component
    FROM action_states as states
    JOIN actions AS a ON states.action = a.id
    JOIN conversations AS c ON a.conv = c.id
    WHERE states.ref = any($1)
    ORDER BY a.id DESC
    LIMIT 1
    """
    actor_in_conv_sql = """
    SELECT r.id
    FROM recipients as r
    JOIN participants AS p ON r.id = p.recipient
    JOIN conversations AS c ON p.conv = c.id
    WHERE c.id = $1 AND c.published = TRUE AND r.address = $2
    """
    latest_message_action_sql = """
    SELECT a.key
    FROM actions AS a
    JOIN conversations AS c ON a.conv = c.id
    WHERE c.id = $1 AND a.message IS NOT NULL
    ORDER BY a.id DESC
    LIMIT 1
    """

    async def process_smtp_message(self, smtp_content: str):
        # TODO deal with non multipart
        msg: Message = email.message_from_string(smtp_content)
        # debug(dict(msg))
        if msg['EM2-ID']:
            # this is an em2 message and should be received via the proper route too
            return

        _, actor_addr = email.utils.parseaddr(msg['From'])
        assert actor_addr, actor_addr
        actor_addr = actor_addr.lower()

        recipients = email.utils.getaddresses(msg.get_all('To', []) + msg.get_all('Cc', []))
        recipients = [a for n, a in recipients]
        # TODO check at least one recipient is associated with this domain
        timestamp = to_utc_naive(email.utils.parsedate_to_datetime(msg['Date']))
        async with self.db.acquire() as conn:
            conv_id = parent_key = parent_component = actor_id = None
            # find which conversation this relates to
            msg_ids = set()
            for f in (msg['In-Reply-To'], msg['References']):
                msg_ids.update(msg_id.strip('<> ') for msg_id in (f or '').split('\n') if msg_id)
            r = await conn.fetchrow(self.find_from_refs_sql, msg_ids)
            if r:
                conv_id, parent_key, parent_component = r

            if conv_id:
                actor_id = await conn.fetchval(self.actor_in_conv_sql, conv_id, actor_addr)
                if not actor_id:
                    logger.warning('actor "%s" not associated with conversation %d', actor_addr, conv_id)
                    raise HTTPForbidden(text='from address not associated with the conversation')

            recipient_lookup = await create_missing_recipients(conn, recipients)
            recipients_ids = list(recipient_lookup.values())

            body = get_smtp_body(msg, smtp_content)
            if conv_id:
                if body:
                    if parent_component == Components.MESSAGE:
                        add_msg_parent_key = parent_key
                    else:
                        add_msg_parent_key = await conn.fetchval(self.latest_message_action_sql, conv_id)

                    apply_action = ApplyAction(
                        conn,
                        remote_action=True,
                        action_key=gen_random('smtp'),
                        conv=conv_id,
                        published=True,
                        actor=actor_id,
                        timestamp=timestamp,
                        component=Components.MESSAGE,
                        verb=Verbs.ADD,
                        item=gen_random('msg'),
                        parent=add_msg_parent_key,
                        body=body,
                        relationship=Relationships.SIBLING,
                    )
                    await apply_action.run()
                    action_id = apply_action.action_id

                # TODO more actions to add any extra recipients to the conversation
                assert recipients_ids
            else:
                creator = CreateForeignConv(conn)
                action_key = gen_random('smtp')
                msg_key = gen_random('msg')
                subject = msg['Subject'] or '-'
                conv_id, action_id = await creator.run(action_key, {
                    'details': {
                        'key': generate_conv_key(actor_addr, timestamp, subject),
                        'creator': actor_addr,
                        'subject': subject,
                        'ts': timestamp,
                    },
                    'participants': [{'address': r} for r in recipients + [actor_addr]],
                    'messages': [{
                        'key': msg_key,
                        'body': body or '',
                    }],
                    'actions': [{
                        'key': action_key,
                        'verb': Verbs.PUBLISH,
                        'component': None,
                        'body': body,
                        'ts': timestamp,
                        'actor': actor_addr,
                        'message': msg_key,
                    }]
                })
            msg_id = msg.get('Message-ID', '').strip('<> ')
            await conn.execute("""
            INSERT INTO action_states (action, ref, status) VALUES ($1, $2, 'successful')
            """, action_id, msg_id)
        await self.pusher.push(action_id, transmit=False)


class LogFallbackHandler(FallbackHandler):
    async def send_message(self, *, e_from: str, to: List[str], bcc: List[str], subject: str, body: str,
                           action: Action):
        plain_body = self.plain_format(body, action.conv_key)
        logger.info('%s > %s, subject: "%s"\n%s', e_from, to, subject, indent(plain_body, '  '))
