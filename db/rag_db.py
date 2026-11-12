vector_ebedding="""
CREATE EXTENSION IF NOT EXISTS vector;
"""

embedding_table="""
CREATE TABLE product_embeddings(
    id INTEGER REFERENCES public.sku_catalogue(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""