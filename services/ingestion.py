
import asyncpg
from core.logging import get_logger, setup_logging
setup_logging()
logger = get_logger(__name__)


async def insert_csv_data(pool: asyncpg.Pool, data_buffer, has_header: bool = False) -> None:
    async with pool.acquire() as conn:
        try:
            logger.info("Starting COPY operation...")
            await conn.copy_to_table(
                "csv_records", 
                source=data_buffer, 
                format='csv',
                header=has_header,
                columns=["name", "sku", "description"]
            )
            logger.info("COPY operation finished successfully.")
        except Exception as db_err:
            logger.error(f"DATABASE ERROR: {db_err}")
            raise 