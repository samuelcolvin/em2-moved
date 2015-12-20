from em2.models import Conversation


def test_con_factory(Session, conversation_factory):
    session = Session()
    assert session.query(Conversation).count() == 0
    conversation = conversation_factory()
    assert session.query(Conversation).count() == 1
    assert conversation.global_id.startswith('con_')
