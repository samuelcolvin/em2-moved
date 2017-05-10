import os
import pytest

from em2 import Settings
from em2.ds import DataStore


def test_unchanged():
    settings = Settings()
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 0.8


def test_changed():
    settings = Settings(COMMS_HEAD_REQUEST_TIMEOUT=123)
    assert settings.COMMS_HEAD_REQUEST_TIMEOUT == 123


def test_invalid():
    with pytest.raises(TypeError):
        Settings(FOOBAR=123)


def test_settings_load_module_good():
    # had to use the base datastore here as the postgres one requires the database to already exist
    s = Settings()
    assert issubclass(s.datastore_cls, DataStore)


def test_settings_load_module_bad_ds_cls():
    with pytest.raises(ImportError) as excinfo:
        Settings(DATASTORE_CLS='foobar').datastore_cls
    assert excinfo.value.args[0] == "foobar doesn't look like a module path"
    with pytest.raises(ImportError) as excinfo:
        Settings(DATASTORE_CLS='em2.ds.pg.datastore.missing').datastore_cls
    assert excinfo.value.args[0] == 'Module "em2.ds.pg.datastore" does not define a "missing" attribute'


def test_environ_substitution():
    settings = Settings()
    assert settings.COMMS_DNS_CACHE_EXPIRY == 7200
    assert settings.LOCAL_DOMAIN == 'no-domain-set'
    os.environ['EM2_COMMS_DNS_CACHE_EXPIRY'] = '1234'
    os.environ['EM2_LOCAL_DOMAIN'] = 'example.com'

    settings2 = Settings()
    assert settings2.COMMS_DNS_CACHE_EXPIRY == 1234
    assert settings2.LOCAL_DOMAIN == 'example.com'
    os.environ.pop('EM2_COMMS_DNS_CACHE_EXPIRY')
    os.environ.pop('EM2_LOCAL_DOMAIN')