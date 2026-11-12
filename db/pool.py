import asyncio
import asyncpg
from core.config import settings
from pgvector.asyncpg import register_vector
from core.logging import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """Manages the lifecycle of the asyncpg connection pool."""

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> asyncpg.Pool:
        """Create and cache an asyncpg connection pool.

        Thread-safe singleton implementation using double-checked locking.
        """
        if self._pool is not None:
            return self._pool

        async with self._lock:
            # Re-check after acquiring lock to prevent race condition
            if self._pool is not None:
                return self._pool

            logger.info("db_pool_initializing", dsn=settings.database_url.split("@")[-1])
            self._pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=5,
                max_size=20,
                command_timeout=60,
                init=register_vector,
            )
            logger.info("db_pool_initialized")
            return self._pool

    async def disconnect(self) -> None:
        """Gracefully close the connection pool."""
        async with self._lock:
            if self._pool is not None:
                await self._pool.close()
                self._pool = None
                logger.info("db_pool_closed")

    def get_pool(self) -> asyncpg.Pool:
        """Return the current pool; raises if not initialised."""
        if self._pool is None:
            raise RuntimeError(
                "Database pool is not initialised. "
                "Ensure db.connect() was called during startup."
            )
        return self._pool

db = DatabaseManager()

async def create_pool(): return await db.connect()
async def close_pool(): await db.disconnect()
def get_pool(): return db.get_pool()
