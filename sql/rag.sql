CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE product_embeddings(
    id INTEGER PRIMARY KEY REFERENCES public.sku_catalogue(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    dense_embedding vector(384),
    sparse_embedding sparsevec(30522),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON product_embeddings
USING hnsw (dense_embedding vector_cosine_ops);

CREATE INDEX ON product_embeddings
USING hnsw (sparse_embedding sparsevec_inner_product_ops);