vector_embedding = """
CREATE EXTENSION IF NOT EXISTS vector;
"""

embedding_table = """
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
"""