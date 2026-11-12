from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import redis.asyncio as redis

from tasks.embedding_worker import backfill_embeddings_task
from tasks.rag_worker import rag_query_task, rag_retrieve_task
from core.logging import get_logger
from core.config import settings
import asyncio
from schema.ragSchema import RAGQueryRequest

logger = get_logger(__name__)
_redis_pool = redis.ConnectionPool.from_url(settings.redis_url)


rag_router = APIRouter(prefix="/api/v1", tags=["RAG"])


@rag_router.post("/trigger-backfill")
async def trigger():
    logger.info("trigger_backfill_endpoint_hit")
    task = await backfill_embeddings_task.kicker().kiq()
    logger.info("backfill_task_dispatched")
    return {"status": "queued", "task_id": task.task_id}



@rag_router.post("/rag_retrieve")
async def rag_retrieve(request: RAGQueryRequest):
    """
    Dispatches a retrieve-only task (embed → hybrid search → rerank).
    Returns the task_id; poll the result backend for the top-5 chunks.
    """
    query = request.query.strip()
    if not query:
        return {"status": "error", "message": "Query cannot be empty"}

    task = await rag_retrieve_task.kicker().kiq(query)
    result = await task.wait_result()
    return result



@rag_router.post("/rag_generate")
async def rag_generate(request: RAGQueryRequest):
    """
    Dispatches a full RAG task (retrieve → LLM generation).
    Streams the LLM response back as Server-Sent Events.
    """
    query = request.query.strip()
    if not query:
        return {"status": "error", "message": "Query cannot be empty"}

    task = await rag_query_task.kicker().kiq(query)
    task_id = task.task_id

    async def event_generator():

        r = redis.Redis(connection_pool=_redis_pool)
        pubsub = r.pubsub()
        channel = f"stream:{task_id}"
        
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                token = message["data"].decode("utf-8")

                if token == "[DONE]":
                    break

                yield token

        except asyncio.CancelledError:
            logger.info("client_disconnected", task_id=task_id)
            raise

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await r.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
    )