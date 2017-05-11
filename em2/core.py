import hashlib
from enum import Enum, unique
from typing import List

from pydantic import BaseModel, EmailStr, constr


def hash_id(*args, sha256=False):
    to_hash = '_'.join(map(str, args)).encode()
    if sha256:
        return hashlib.sha256(to_hash).hexdigest()
    else:
        return hashlib.sha1(to_hash).hexdigest()


@unique
class Components(str, Enum):
    """
    Component types, used for both urls and in db ENUM see models.sql
    """
    SUBJECT = 'sbj'
    EXPIRY = 'xpr'
    LABEL = 'lbl'
    MESSAGE = 'msg'
    PARTICIPANT = 'prt'
    ATTACHMENT = 'atc'


@unique
class Verbs(str, Enum):
    """
    Verb types, used for both urls and in db ENUM see models.sql
    """
    ADD = 'add'
    MODIFY = 'mod'
    DELETE = 'del'
    LOCK = 'lck'
    UNLOCK = 'ulk'


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update is slightly ugly, but should happen vary rarely.
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def set_recipient(request):
    if request['session'].recipient_id:
        return
    recipient_id = await request['conn'].fetchval(GET_RECIPIENT_ID, request['session'].address)
    if recipient_id is None:
        recipient_id = await request['conn'].fetchval(SET_RECIPIENT_ID, request['session'].address)
    request['session'].recipient_id = recipient_id
    # until samuelcolvin/pydantic#14 is fixed
    request['session'].__values__['recipient_id'] = recipient_id
    request['session_change'] = True


LIST_CONVS = """
SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
FROM (
  SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  LEFT OUTER JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1
  ORDER BY c.id DESC LIMIT 50
) t;
"""


async def convs_json(request):
    return await request['conn'].fetchval(LIST_CONVS, request['session'].recipient_id)


CONV_DETAILS = """
SELECT row_to_json(t)
FROM (
  SELECT c.id as id, c.hash as hash, c.subject as subject, c.timestamp as ts
  FROM conversations AS c
  JOIN participants ON c.id = participants.conversation
  WHERE participants.recipient = $1 AND c.hash = $2
) t;
"""


async def conv_details(request, conv_id):
    return await request['conn'].fetchval(CONV_DETAILS, request['session'].recipient_id, conv_id)


class CreateConvModel(BaseModel):
    subject: constr(max_length=255) = ...
    message: str = ...
    participants: List[EmailStr] = []


GET_EXISTING_RECIPIENTS = 'SELECT id, address FROM recipients WHERE address = any($1)'
SET_MISSING_RECIPIENTS = """
INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
RETURNING id
"""
CREATE_CONV = """
INSERT INTO conversations (creator, subject)
VALUES ($1, $2) RETURNING id
"""
ADD_PARTICIPANT = 'INSERT INTO participants (conversation, recipient) VALUES ($1, $2)'
ADD_MESSAGE = 'INSERT INTO messages (hash, conversation, body) VALUES ($1, $2, $3)'


async def create_conv(request, conv: CreateConvModel):
    conn = request['conn']
    participant_addresses = set(conv.participants)
    participant_ids = set()
    if participant_addresses:
        for r in await conn.fetch(GET_EXISTING_RECIPIENTS, participant_addresses):
            participant_ids.add(r['id'])
            participant_addresses.remove(r['address'])

        if participant_addresses:
            extra_ids = {r['id'] for r in await conn.fetch(SET_MISSING_RECIPIENTS, participant_addresses)}
            participant_ids.update(extra_ids)

    conv_id = await conn.fetchval(CREATE_CONV, request['session'].recipient_id, conv.subject)
    if participant_ids:
        await conn.executemany(ADD_PARTICIPANT, {(conv_id, pid) for pid in participant_ids})
    message_hash = hash_id(request['session'].address, conv.message)
    await conn.execute(ADD_MESSAGE, message_hash, conv_id, conv.message)
    return conv_id
