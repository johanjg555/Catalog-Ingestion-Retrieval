import asyncpg



from core.logging import get_logger, setup_logging

setup_logging()
logger=get_logger(__name__)

CSV_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.sku_catalogue
(
    id SERIAL PRIMARY KEY,
    name text,
    sku text,
    description text
);
"""

RAG_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.product_chunks (
    chunk_id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES public.sku_catalogue(id) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL,
    content TEXT NOT NULL,
    dense_embedding vector(384),
    sparse_embedding sparsevec(30522),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS product_chunks_dense_idx ON public.product_chunks
USING hnsw (dense_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS product_chunks_sparse_idx ON public.product_chunks
USING hnsw (sparse_embedding sparsevec_ip_ops);
"""


async def check_and_create_table(pool: asyncpg.Pool) -> None:
    """Check if the target tables exist, and create them if not."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(CSV_TABLE_SQL)
            await conn.execute(RAG_TABLES_SQL)
    logger.info("Checked for tables existence and created if necessary.")




