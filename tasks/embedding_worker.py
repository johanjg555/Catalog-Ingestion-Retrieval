"""
Taskiq task for embedding backfill.

Delegates to the rag_pipeline service so the core logic remains
reusable and testable outside of the task queue.
"""

from __future__ import annotations

import asyncio
import time

from taskiq import Context, TaskiqDepends
from broker import rag_broker
from services.rag_pipeline import fetch_and_format_chunks, insert_chunks_to_db, fetch_missing_ids
from core.logging import get_logger
from pgvector.asyncpg import SparseVector
from utils.rag_utils import get_dense_model, get_sparse_model

logger = get_logger(__name__)

BATCH_SIZE = 16
INSERT_BATCH_SIZE = 32
SUB_BATCH_SIZE = 32

DIMENSIONS = 30522

embedding_limit = asyncio.Semaphore(1)


@rag_broker.task(retry_on_error=True, max_retries=3)
async def backfill_embeddings_task(
    context: Context = TaskiqDepends()
) -> dict:
    logger.info("backfill_master_task_start")

    try:
        pool = context.state.db.get_pool()
        total_queued = 0
        last_id = 0

        while True:
            ids = await fetch_missing_ids(pool, last_id=last_id, limit=BATCH_SIZE)
            if not ids:
                break

            await embed_and_save_task.kiq(ids)

            total_queued += len(ids)
            last_id = ids[-1]

            logger.info(
                "backfill_enqueued_batch",
                batch_size=len(ids),
                last_id=last_id,
            )

            if len(ids) < BATCH_SIZE:
                break

            await asyncio.sleep(5)

        logger.info("backfill_enqueued", total_rows=total_queued)
        return {"status": "success", "queued": total_queued}

    except Exception as e:
        logger.exception("backfill_master_task_failed", error=str(e))
        raise





@rag_broker.task(retry_on_error=True, max_retries=3)
async def embed_and_save_task(
    ids: list[int],
    context: Context = TaskiqDepends()
) -> None:
    async with embedding_limit:
        try:
            pool = context.state.db.get_pool()
            model = get_dense_model()
            sparse_model = get_sparse_model()

            valid_ids, chunk_types, contents = await asyncio.wait_for(
                fetch_and_format_chunks(pool, ids),
                timeout=60.0,
            )

            if not valid_ids:
                return

            logger.info("starting_embedding", total_chunks=len(valid_ids))
            start = time.monotonic()


            for i in range(0, len(contents), SUB_BATCH_SIZE):
                sub_batch = contents[i : i + SUB_BATCH_SIZE]
                
                logger.info(
                    "embedding_sub_batch", 
                    offset=i, 
                    count=len(sub_batch), 
                    total=len(contents)
                )


                async with asyncio.TaskGroup() as tg:
            
                   dense_task = tg.create_task(asyncio.to_thread(
                        lambda batch=sub_batch: list(model.passage_embed(batch))
                    ))
                   sparse_task = tg.create_task(asyncio.to_thread(
                        lambda batch=sub_batch: list(sparse_model.passage_embed(batch))
                    ))

                dense_embeddings = dense_task.result()
                sparse_embeddings = sparse_task.result()

                logger.info("dense_embeddings_generated", count=len(dense_embeddings))
                logger.info("sparse_embeddings_generated", count=len(sparse_embeddings))

        
                batch_records = []

                for id_, c_type, content, dense, sparse in zip(
                    valid_ids,
                    chunk_types,
                    contents,
                    dense_embeddings,
                    sparse_embeddings,
                ):
                    
                    sparse_dict = dict(zip(sparse.indices.tolist(), sparse.values.tolist()))
                    sparse_obj = SparseVector(sparse_dict, DIMENSIONS)
                    
                    batch_records.append((
                        id_, 
                        c_type,
                        content, 
                        dense.tolist(), 
                        sparse_obj
                    ))

                    if len(batch_records) >= INSERT_BATCH_SIZE:
                        await asyncio.wait_for(
                            insert_chunks_to_db(pool, batch_records),
                            timeout=90,
                        )
                        batch_records.clear()

                if batch_records:
                    await asyncio.wait_for(
                        insert_chunks_to_db(pool, batch_records),
                        timeout=90,
                    )

            logger.info(
                "batch_complete",
                total_chunks=len(valid_ids),
                duration=round(time.monotonic() - start, 2),
            )

        except asyncio.TimeoutError:
            logger.error("task_timeout", ids_count=len(ids))
            raise
        except Exception as e:
            logger.exception("embed_task_failed", error=str(e))
            raise