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

CREATE TABLE IF NOT EXISTS product_embeddings (
    id INTEGER REFERENCES public.sku_catalogue(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    dense_embedding vector(384),
    sparse_embedding sparsevec(30522),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS product_embeddings_dense_idx ON product_embeddings
USING hnsw (dense_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS product_embeddings_sparse_idx ON product_embeddings
USING hnsw (sparse_embedding sparsevec_cosine_ops);
"""


async def check_and_create_table(pool: asyncpg.Pool) -> None:
    """Check if the target tables exist, and create them if not."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(CSV_TABLE_SQL)
            await conn.execute(RAG_TABLES_SQL)
    logger.info("Checked for tables existence and created if necessary.")





