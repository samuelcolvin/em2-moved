import base64
import hashlib
import os
from enum import Enum, unique


def hash_id(*args, sha256=False):
    to_hash = '_'.join(map(str, args)).encode()
    if sha256:
        return hashlib.sha256(to_hash).hexdigest()
    else:
        return hashlib.sha1(to_hash).hexdigest()


def gen_message_key():
    return base64.b32encode(os.urandom(10))[:16].decode().lower()


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
