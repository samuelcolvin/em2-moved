import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from em2pg.models import Conversation


def test_create_retrieve_conversation(Session):
    session = Session()
    assert session.query(Conversation).count() == 0
    con = Conversation(
        con_id='x',
        creator='user@example.com',
        subject='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    assert session.query(Conversation).count() == 0
    session.add(con)
    assert session.query(Conversation).count() == 1


def test_create_conversation_duplicate_id(Session):
    session = Session()
    assert session.query(Conversation).count() == 0
    con1 = Conversation(
        con_id='x',
        creator='user@example.com',
        subject='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    session.add(con1)
    assert session.query(Conversation).count() == 1
    con2 = Conversation(
        con_id='x',
        creator='user2@example.com',
        subject='testing',
        timestamp=datetime.datetime.now(),
        status='draft',
    )
    session.add(con2)
    with pytest.raises(IntegrityError):
        session.flush()
