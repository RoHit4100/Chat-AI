import os
import logging
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

class CheckpointerManager:
    """Manages the lifecycle of the AsyncPostgresSaver connection pool."""

    def __init__(self):
        self.pool: AsyncConnectionPool | None = None
        self.saver = None

    async def start(self):
        """Create pool, connect, and run setup() for checkpoint tables."""
        use_sqlite = os.getenv("USE_SQLITE", "0").lower() in ("1", "true")
        db_url = os.getenv("DATABASE_URL", "")

        if use_sqlite or not db_url.startswith("postgres"):
            logger.info("Using in-memory checkpointer.")
            self.saver = MemorySaver()
            return self.saver

        try:
            self.pool = AsyncConnectionPool(
                conninfo=db_url,
                max_size=20,
                open=False,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            )
            await self.pool.open()
            self.saver = AsyncPostgresSaver(conn=self.pool)
            await self.saver.setup()
            logger.info("AsyncPostgresSaver initialized and setup completed.")
            return self.saver
        except Exception as exc:
            logger.warning("Postgres pool init failed (%s); using in-memory saver fallback.", exc)
            self.saver = MemorySaver()
            return self.saver

    async def close(self):
        """Explicitly close connection pool on shutdown."""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("Checkpointer connection pool closed.")

checkpointer_manager = CheckpointerManager()

async def get_checkpointer():
    """Return active checkpointer, lazily initializing if not started yet."""
    if checkpointer_manager.saver is None:
        await checkpointer_manager.start()
    return checkpointer_manager.saver
