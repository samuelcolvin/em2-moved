from aiopg.sa import create_engine

from em2.ds.pg.datastore import PostgresDataStore, ConnectionContextManager

pytest_plugins = 'tests.tools.plugins.datastore'


class TestPostgresDataStore(PostgresDataStore):
    _conn_ctx = None

    def connection(self):
        assert self._conn_ctx is None
        self._conn_ctx = TestCtx(self.engine)
        return self._conn_ctx

    def reuse_connection(self):
        assert self._conn_ctx is not None
        return self._conn_ctx

    async def terminate(self):
        if self._conn_ctx is not None:
            await self._conn_ctx.terminate()


class TestCtx(ConnectionContextManager):
    conn = None

    async def __aenter__(self):
        if self.conn is None:
            self.conn = await self._engine._acquire()
            self.tr = await self.conn._begin()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def terminate(self):
        await self.tr.rollback()
        self.tr = None
        self._engine.release(self.conn)
        self.conn = None


async def test_postgres_datastore(loop, db, dsn, ds_test_method):
    async with create_engine(dsn, loop=loop) as engine:
        ds = TestPostgresDataStore(engine)
        try:
            await ds_test_method(ds)
        finally:
            await ds.terminate()
