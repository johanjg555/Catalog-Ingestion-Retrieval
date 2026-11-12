"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Central configuration for the CSV ingestion system.

    All values can be overridden via environment variables or a `.env` file
    placed in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ── PostgreSQL ──────────────────────────────────────────────
    database_url: str = "postgresql://user:password@localhost:5432/csv_ingestion"

    # ── Redis (Taskiq broker) ───────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Ingestion tuning ────────────────────────────────────────
    chunk_size: int = 10_000          # rows per chunk
    max_concurrent_tasks: int = 10    # in-flight Taskiq tasks
    max_retries: int = 3              # retries for failed chunks

    # ── Application ─────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"
    log_file: str = "logs/app.log"


    SECRET_KEY :str= "your-secret-key"
    ALGORITHM :str= "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES :int= 1
    REFRESH_TOKEN_EXPIRE_MINUTES :int= 5
    
    # ── RAG Settings ────────────────────────────────────────────
    sparse_dimensions: int = 30522

    # ── LLM Settings ────────────────────────────────────────────
    model_path: str = "models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"

    llama_server_url: str = "http://localhost:8080/v1"
    

settings = Settings()
