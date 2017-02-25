#!/usr/bin/env python3.6
import asyncio
from em2 import Settings, setup_logging
from em2.utils import check_server

setup_logging()

settings = Settings()
loop = asyncio.get_event_loop()
failed = loop.run_until_complete(check_server(settings))
failed and exit(1)

