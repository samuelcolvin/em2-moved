from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, func, Text, ForeignKey, Boolean, Sequence, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.declarative import declared_attr
from em2.base import Conversations, Verbs, Participants, Components
from .model_extras import TIMESTAMPTZ, RichEnum

Base = declarative_base()


class Conversation(Base):
    __tablename__ = Components.CONVERSATIONS

    class Status(Conversations.Status, RichEnum):
        pass

    id = Column(Integer, Sequence('con_id_seq'), primary_key=True, nullable=False)
    global_id = Column(String(64), index=True, nullable=False)
    creator = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    signature = Column(Text)
    status = Column(Status.enum(), nullable=False)
    expiration = Column(TIMESTAMPTZ)
    subject = Column(String(255), nullable=False)
    labels = Column(ARRAY(String(64)))
    current = Column(JSONB)
    __table_args__ = (
        UniqueConstraint('global_id', name='_con_id'),
    )


class Update(Base):
    __tablename__ = 'updates'

    class ComponentEnum(Components, RichEnum):
        pass

    class VerbEnum(Verbs, RichEnum):
        pass

    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(Integer, Sequence('update_id_seq'), primary_key=True, nullable=False)
    participant = Column(Integer, ForeignKey('participants.id'), nullable=False)
    timestamp = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    component = Column(ComponentEnum.enum(), nullable=False)
    component_id = Column(String(40))
    verb = Column(VerbEnum.enum(), nullable=False)
    value = Column(Text)


class Participant(Base):
    __tablename__ = Components.PARTICIPANTS

    class Permissions(Participants.Permissions, RichEnum):
        pass

    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    id = Column(Integer, Sequence('part_id_seq'), primary_key=True, nullable=False)
    address = Column(String(255), nullable=False)
    display_name = Column(String(255))
    hidden = Column(Boolean, default=False)
    permissions = Column(Permissions.enum())
    __table_args__ = (
        UniqueConstraint('conversation', 'address', name='_participant_email'),
    )


class MsgCmt:
    class Status(RichEnum):
        ACTIVE = 'active'
        DELETED = 'deleted'

    id = Column(String(40), primary_key=True)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(Status.enum(), server_default=Status.ACTIVE)

    @declared_attr
    def author(cls):
        return Column(Integer, ForeignKey('participants.id'), nullable=False)


class Message(MsgCmt, Base):
    __tablename__ = Components.MESSAGES
    conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    parent = Column(String(40), ForeignKey('messages.id', ondelete='CASCADE'))
    locked = Column(Boolean, default=False)


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


# TODO uncomment once we're ready to implement extras:
# class Extra(Base):
#     __tablename__ = Components.EXTRAS
#     conversation = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
#     id = Column(String(40), primary_key=True)
#     author = Column(Integer, ForeignKey('participants.id'), nullable=False)
#     timestamp = Column(TIMESTAMPTZ, nullable=False)
#     type = Column(String(40))
#     name = Column(String(255))
#     description = Column(Text)
#     data = Column(JSONB)
#     questions = Column(JSONB)
#
#
# class Response(Base):
#     __tablename__ = Components.RESPONSES
#     id = Column(String(40), primary_key=True)
#     extra = Column(String(40), ForeignKey('extras.id', ondelete='CASCADE'), nullable=False)
#     author = Column(Integer, ForeignKey('participants.id'), nullable=False)
#     timestamp = Column(TIMESTAMPTZ, nullable=False)
#     response = Column(JSONB, nullable=False)
