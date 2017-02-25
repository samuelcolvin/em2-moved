import asyncio
from em2 import Settings
from em2.utils import check_server


def _check_web():
    settings = Settings()
    url = 'http://' + settings.WEB_BIND
    loop = asyncio.get_event_loop()
    failed = loop.run_until_complete(check_server(url))
    failed and exit(1)
