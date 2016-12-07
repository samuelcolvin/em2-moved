import pytest

from em2 import Settings, create_controller
from em2.core import Controller


def test_unchanged():
    settings = Settings()
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 0.8


def test_changed():
    settings = Settings(COMMS_HEAD_REQUEST_TIMEOUT=123)
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 123


def test_invalid():
    with pytest.raises(TypeError):
        Settings(FOOBAR=123)


def test_create_controller_good():
    # had to use the base datastore here as the postgres one requires the database to already exist
    ctrl = create_controller(DATASTORE_CLS='em2.core.datastore.DataStore')
    assert isinstance(ctrl, Controller)
    assert ctrl.settings.COMMS_HTTP_TIMEOUT == 4


def test_create_controller_bad_ds_cls():
    with pytest.raises(ImportError) as excinfo:
        create_controller(DATASTORE_CLS='foobar')
    assert excinfo.value.args[0] == "foobar doesn't look like a module path"
    with pytest.raises(ImportError) as excinfo:
        create_controller(DATASTORE_CLS='em2.ds.pg.datastore.missing')
    assert excinfo.value.args[0] == 'Module "em2.ds.pg.datastore" does not define a "missing" attribute/class'
