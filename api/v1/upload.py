from __future__ import annotations
import uuid
from anyio import open_file


from fastapi import APIRouter, HTTPException,UploadFile,File,Security

from schema.uploadSchema import UploadResponse
from schema.authSchema import User
from tasks.csv_worker import ingest_csv_task 

from core.config import settings
from core.logging import get_logger, setup_logging
import os
from services.auth import get_current_user



setup_logging()
logger = get_logger(__name__)

upload_router =APIRouter(prefix="/api/v1", tags=["upload"])


@upload_router.post("/upload", response_model=UploadResponse)
async def upload_csv(current_user: User = Security(get_current_user, scopes=["upload"]),
                    file: UploadFile = File(...),
) -> UploadResponse:
    """Endpoint to upload a CSV file and ingest its contents into the database."""
    
    if current_user.disabled:
        raise HTTPException(403, "User is disabled")

    if not file.filename.endswith(".csv") and file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    temp_path = f"/tmp/{current_user.username}_{uuid.uuid4()}.csv"
    
    try:
        async with await open_file(temp_path, mode="wb") as out_file:
            while chunk := await file.read(settings.chunk_size):
                await out_file.write(chunk)

        task=await ingest_csv_task.kicker().kiq(temp_path)
        result=await task.wait_result()
        logger.info(f"Task execution took: {result.execution_time} seconds.")
        if not result.is_err:
            logger.info(f"Returned value: {result.return_value}")
        else:
            logger.error("Error found while executing task.")

    except Exception as e:
        logger.error(f"Error occurred while uploading file: {file.filename}, Error: {str(e)}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        raise HTTPException(status_code=500, detail=str(e))

    return UploadResponse(
        message="File uploaded and data ingested successfully.",
        task_id=task.task_id
        )


