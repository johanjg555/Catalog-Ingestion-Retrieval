from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000,example="How many ports does Catalyst 9600 series have?")