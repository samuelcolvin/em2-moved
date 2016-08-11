import pytest

from em2 import Settings


def test_unchanged():
    settings = Settings()
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 0.8


def test_changed():
    settings = Settings(COMMS_HEAD_REQUEST_TIMEOUT=123)
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 123


def test_invalid():
    with pytest.raises(TypeError):
        Settings(FOOBAR=123)
