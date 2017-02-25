from gunicorn.app.base import BaseApplication

from em2 import Settings, setup_logging
from em2.comms.http import create_app
from em2.ds.pg.utils import prepare_database
from em2.utils import wait_for_services

setup_logging()
settings = Settings()
wait_for_services(settings)
prepare_database(settings, delete_existing=False)

config = dict(
    worker_class='aiohttp.worker.GunicornWebWorker',
    max_requests=5000,
    max_requests_jitter=500,
)


class Application(BaseApplication):
    def load_config(self):
        for k, v in config.items():
            self.cfg.set(k, v)

    def load(self):
        return create_app(settings)


Application().run()
