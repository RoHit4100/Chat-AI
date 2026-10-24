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
        import sys
        use_sqlite = os.getenv("USE_SQLITE", "0").lower() in ("1", "true") or "test" in sys.argv
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

async def adelete_thread_checkpoints(thread_id: str):
    """Delete all checkpoint records for a thread from the checkpointer to prevent orphaned storage bloat."""
    saver = await get_checkpointer()
    if isinstance(saver, MemorySaver):
        saver.storage.pop(str(thread_id), None)
        if hasattr(saver, "writes"):
            saver.writes.pop(str(thread_id), None)
        return

    if checkpointer_manager.pool is not None:
        try:
            async with checkpointer_manager.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (str(thread_id),))
                    await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (str(thread_id),))
                    await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (str(thread_id),))
            logger.info("Deleted postgres checkpoints for thread %s", thread_id)
        except Exception as exc:
            logger.warning("Failed to delete postgres checkpoints for thread %s: %s", thread_id, exc)

def delete_thread_checkpoints(thread_id: str):
    """Synchronous wrapper to delete checkpoints for a thread."""
    try:
        from asgiref.sync import async_to_sync
        async_to_sync(adelete_thread_checkpoints)(thread_id)
    except Exception as exc:
        logger.warning("delete_thread_checkpoints failed: %s", exc)

async def aprune_thread_checkpoints(thread_id: str, keep_last: int = 10):
    """Prune older checkpoint records for a thread to prevent database bloat."""
    if checkpointer_manager.pool is not None:
        try:
            async with checkpointer_manager.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        DELETE FROM checkpoints
                        WHERE thread_id = %s
                          AND checkpoint_id NOT IN (
                              SELECT checkpoint_id FROM checkpoints
                              WHERE thread_id = %s
                              ORDER BY checkpoint_id DESC
                              LIMIT %s
                          )
                        """,
                        (str(thread_id), str(thread_id), keep_last),
                    )
            logger.info("Pruned older checkpoints for thread %s (kept %s)", thread_id, keep_last)
        except Exception as exc:
            logger.debug("aprune_thread_checkpoints skipped/failed for %s: %s", thread_id, exc)
