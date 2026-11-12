

from core.config import settings
from core.logging import setup_logging, get_logger
from db.pool import get_pool
from services.ingestion import insert_csv_data
from anyio import open_file
import os
import io
import csv

from broker import broker


setup_logging()
logger = get_logger(__name__)



@broker.task(retry_on_error=True, max_retries=3)
async def process_chunk_task(chunk: list[list[str]]):
    pool=get_pool()
    buffer = io.BytesIO()
    text_wrapper = io.TextIOWrapper(buffer, encoding="utf-8", newline="")

    writer = csv.writer(text_wrapper)
    writer.writerows(chunk)

    text_wrapper.flush()
    buffer.seek(0)

    await insert_csv_data(pool, buffer, has_header=False)



@broker.task
async def ingest_csv_task(file_path: str) -> dict:
    logger.info(f"Orchestrator starting: {file_path}")
    chunk_size = 10000

    try:
        # newline='' is critical for the csv module to handle line endings correctly
        with open(file_path, mode='r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
          
            header = next(reader, None)

            chunk = []

            for row in reader:
                chunk.append(row)

                if len(chunk) >= chunk_size:
                    await process_chunk_task.kiq(chunk)
                    chunk = []

            # send remaining rows
            if chunk:
                await process_chunk_task.kiq(chunk)
        return {"status": "chunks_queued"}
        


    except Exception as e:
        logger.error(f"Orchestrator failed: {e}")
        raise e
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)