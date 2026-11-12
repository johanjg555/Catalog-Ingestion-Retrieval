"""Taskiq broker configuration.

Uses Redis as the message broker for distributing CSV chunk processing
tasks across parallel workers.
"""

from taskiq import TaskiqState, TaskiqEvents

from core.logging import setup_logging, get_logger
from db.pool import db
from db.queries import check_and_create_table

from taskiq_redis import RedisAsyncResultBackend
from taskiq_aio_pika import AioPikaBroker

logger = get_logger(__name__)


csv_result_backend = RedisAsyncResultBackend("redis://localhost:6379/0")
rag_result_backend = RedisAsyncResultBackend("redis://localhost:6379/1")



broker = AioPikaBroker(
    "amqp://guest:guest@localhost:5672",
    queue_name="csv_ingestion"
).with_result_backend(csv_result_backend)



rag_broker = AioPikaBroker(
    "amqp://guest:guest@localhost:5672",
    queue_name="rag_chunk"
).with_result_backend(rag_result_backend)





@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState) -> None:
    setup_logging()
    pool = await db.connect()
    state.db = db
    await check_and_create_table(pool)
    logger.info("broker_started")

@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState) -> None:
    await state.db.disconnect()
    logger.info("broker_stopped")


#rag broker
@rag_broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def rag_startup(state: TaskiqState) -> None:
    setup_logging()
    await db.connect()
    state.db = db
    logger.info("rag_broker_started")

@rag_broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def rag_shutdown(state: TaskiqState) -> None:
    await state.db.disconnect()
    logger.info("rag_broker_stopped")
