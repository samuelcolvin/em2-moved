from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, func, Text, ForeignKey, Boolean, Enum, Sequence
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

Base = declarative_base()
TIMESTAMPTZ = DateTime(timezone=True)

CONVERSATION_STATUS = Enum(
    'pending'
    'active',
    'expired',
    'deleted',
    name='conversation_status'
)


class Conversation(Base):
    __tablename__ = 'conversations'
    id = Column(Integer, Sequence('con_id_seq'), primary_key=True, nullable=False)
    global_id = Column(String(64), index=True, nullable=False)
    creator = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    signature = Column(Text)
    status = Column(CONVERSATION_STATUS)
    expiration = Column(TIMESTAMPTZ)
    subject = Column(String(255), nullable=False)
    labels = Column(ARRAY(String(64)))
    current = Column(JSONB)


class Update(Base):
    __tablename__ = 'updates'
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(Integer, Sequence('con_id_seq'), primary_key=True, nullable=False)
    author = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    action = Column(String(64))
    value = Column(Text, nullable=False)


PARTICIPANT_PERMISSIONS = Enum(
    'full'
    'write',
    'comment',
    'read',
    name='participant_permission'
)


class Participant(Base):
    __tablename__ = 'participants'
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'),
                          nullable=False, primary_key=True)
    email = Column(String(255), nullable=False, primary_key=True)
    display_name = Column(String(255))
    hidden = Column(Boolean, default=False)
    permissions = Column(PARTICIPANT_PERMISSIONS)


MSGCMT_STATUS = Enum(
    'active'
    'deleted',
    name='msgcmt_status'
)


class MsgCmt:
    id = Column(String(40), primary_key=True)
    author = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(MSGCMT_STATUS)


class Message(MsgCmt, Base):
    __tablename__ = 'messages'
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)


class Comment(MsgCmt, Base):
    __tablename__ = 'comments'
    message = Column(String(40), ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    ref = Column(String(40))


class Attachment(Base):
    __tablename__ = 'attachments'
    id = Column(String(40), primary_key=True)
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    path = Column(String(255), nullable=False)
    hash = Column(String(64), nullable=False)
    generator = Column(JSONB)
    expires = Column(TIMESTAMPTZ)


class Extra(Base):
    __tablename__ = 'extras'
    id = Column(String(40), primary_key=True)
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    author = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    type = Column(String(40))
    name = Column(String(255))
    description = Column(Text)
    data = Column(JSONB)
    questions = Column(JSONB)


class Response(Base):
    __tablename__ = 'responses'
    id = Column(Integer, Sequence('response_id_seq'), primary_key=True, nullable=False)
    extra = Column(String(40), ForeignKey('extras.id', ondelete='CASCADE'), nullable=False)
    author = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    response = Column(JSONB, nullable=False)
