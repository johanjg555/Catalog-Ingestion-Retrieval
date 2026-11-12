from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.v1.login import login_router
from api.v1.upload import upload_router
from api.v1.rag import rag_router

from db.pool import db
import uvicorn

from core.logging import get_logger, setup_logging
from broker import broker,rag_broker


logger=get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown resources."""
    setup_logging()
    logger.info("Starting application with settings")  
    app.state.pool = await db.connect()
    
    logger.info("Database connection pool created successfully.")
    if not broker.is_worker_process:
        await broker.startup()
    if not rag_broker.is_worker_process:
        await rag_broker.startup()
    

    yield

    logger.info("Shutting down application, closing database pool.")
    if not rag_broker.is_worker_process:
        await rag_broker.shutdown()
    if not broker.is_worker_process:
        await broker.shutdown()
        
    await db.disconnect() 
    logger.info("Database connection pool closed successfully.")
    logger.info("Application shutdown complete.")

app = FastAPI(
    title="CSV Ingestion Service",
    lifespan=lifespan,
)

app.include_router(login_router)
app.include_router(upload_router)
app.include_router(rag_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness check."""
    return {"status": "ok"}


if __name__ == "__main__":


    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["app.log"],
    )