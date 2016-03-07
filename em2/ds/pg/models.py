from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, func, Text, ForeignKey, Boolean, Sequence, UniqueConstraint, sql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.declarative import declared_attr

from em2.core import Verbs, Participants, Components, Conversations
from .model_extras import TIMESTAMPTZ, SAEnum

Base = declarative_base()


class Conversation(Base):
    __tablename__ = Components.CONVERSATIONS

    class Status(SAEnum, Conversations.Status):
        pass

    id = Column(Integer, Sequence('con_id_seq'), primary_key=True, nullable=False)
    conv_id = Column(String(64), index=True, nullable=False)
    draft_conv_id = Column(String(64))
    creator = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    signature = Column(Text)
    status = Column(Status.sa_enum(), nullable=False)
    ref = Column(String(255), nullable=False)
    expiration = Column(TIMESTAMPTZ)
    subject = Column(String(255), nullable=False)
    labels = Column(ARRAY(String(64)))
    current = Column(JSONB)
    __table_args__ = (
        UniqueConstraint('conv_id', name='_conv_id'),
    )

sa_conversations = Conversation.__table__


class Event(Base):
    __tablename__ = 'events'

    class ComponentEnum(SAEnum, Components):
        pass

    class VerbEnum(SAEnum, Verbs):
        pass

    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(String(40), primary_key=True, nullable=False)
    seq_id = Column(Integer, Sequence('update_id_seq'), index=True, nullable=False)
    actor = Column(Integer, ForeignKey('participants.id'), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    component = Column(ComponentEnum.sa_enum(), nullable=False)
    item = Column(String(40))
    verb = Column(VerbEnum.sa_enum(), nullable=False)
    data = Column(JSONB)  # TODO (maybe) possibly we only want "value" so this could be replaced by a text field

sa_events = Event.__table__


class Participant(Base):
    __tablename__ = Components.PARTICIPANTS

    class Permissions(Participants.Permissions, SAEnum):
        pass

    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(Integer, Sequence('part_id_seq'), primary_key=True, nullable=False)
    address = Column(String(255), nullable=False)
    display_name = Column(String(255))
    hidden = Column(Boolean, default=False)
    permissions = Column(Permissions.sa_enum())

    __table_args__ = (
        UniqueConstraint('conversation', 'address', name='_participant_email'),
    )

sa_participants = Participant.__table__


class MsgCmt:
    class Status(SAEnum):
        ACTIVE = 'active'
        DELETED = 'deleted'

    id = Column(String(40), primary_key=True)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(Status.sa_enum(), server_default=Status.ACTIVE)

    @declared_attr
    def author(cls):
        return Column(Integer, ForeignKey('participants.id'), nullable=False)


class Message(MsgCmt, Base):
    __tablename__ = Components.MESSAGES
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    parent = Column(String(40), ForeignKey('messages.id', ondelete='CASCADE'))
    locked = Column(Boolean, server_default=sql.expression.false())

sa_messages = Message.__table__


class Comment(MsgCmt, Base):
    __tablename__ = Components.COMMENTS
    message = Column(String(40), ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    ref = Column(String(40))


class Attachment(Base):
    __tablename__ = Components.ATTACHMENTS
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(String(40), primary_key=True)
    author = Column(Integer, ForeignKey('participants.id'), nullable=False)
    name = Column(String(255), nullable=False)
    path = Column(String(255), nullable=False)
    hash = Column(String(64), nullable=False)
    generator = Column(JSONB)
    expires = Column(TIMESTAMPTZ)
