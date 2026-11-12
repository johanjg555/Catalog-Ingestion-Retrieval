from __future__ import annotations

from pydantic import BaseModel, Field



class UploadResponse(BaseModel):
    """Standard response model."""

    message: str = Field(..., description="Response message")
    task_id: str = Field(..., description="Task ID")