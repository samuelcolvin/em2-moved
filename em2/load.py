import asyncio
from importlib import import_module

from .core.controller import Controller
from .logging import setup_logging
from .settings import Settings


def import_string(dotted_path):
    """
    Stolen from django. Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError as e:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from e

    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError('Module "%s" does not define a "%s" attribute/class' % (module_path, class_name)) from e


def create_controller(loop=None, **extra_settings):
    setup_logging()  # TODO allow logging to be customised
    loop = loop or asyncio.get_event_loop()
    settings = Settings(**extra_settings)

    ds_cls = import_string(settings.DATASTORE_CLS)
    ds = ds_cls(settings=settings, loop=loop)
    loop.run_until_complete(ds.prepare())

    pusher_cls = import_string(settings.PUSHER_CLS)
    pusher = pusher_cls(settings=settings, loop=loop)
    return Controller(ds, pusher, settings)
