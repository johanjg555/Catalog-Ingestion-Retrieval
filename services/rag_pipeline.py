import asyncio

import asyncpg
from fastembed.rerank.cross_encoder import TextCrossEncoder

from utils.rag_utils import chunk_product, get_dense_model, get_sparse_model, get_reranker
from pgvector.asyncpg import SparseVector
from core.config import settings
from core.logging import get_logger


logger = get_logger(__name__)


#----------------------------- Embedding worker functions---------------------------

async def fetch_missing_ids(
    pool: asyncpg.Pool,
    last_id: int,
    limit: int,
) -> list[int]:
    rows = await pool.fetch(
        """
        SELECT s.id
        FROM sku_catalogue s
        WHERE s.id > $1
        ORDER BY s.id
        LIMIT $2
        """,
        last_id,
        limit,
    )
    return [row["id"] for row in rows]



async def fetch_and_format_chunks(
    pool: asyncpg.Pool,
    ids: list[int],
) -> tuple[list[int], list[str], list[str]]:
    """
    Fetch full rows and convert them into chunks for embedding.
    Returns: (product_ids, chunk_types, contents)
    """
    rows = await pool.fetch(
        "SELECT * FROM sku_catalogue WHERE id = ANY($1::int[])",
        ids,
    )

    all_product_ids: list[int] = []
    chunk_types: list[str] = []
    contents: list[str] = []

    for row in rows:
        product_id = row["id"]
        product_chunks = chunk_product(dict(row))
        for c_type, c_content in product_chunks:
            all_product_ids.append(product_id)
            chunk_types.append(c_type)
            contents.append(c_content)

    return all_product_ids, chunk_types, contents


async def insert_chunks_to_db(
    pool: asyncpg.Pool, 
    records: list[tuple[int, str, str, list[float], dict[int, float]]]
) -> None:
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO product_chunks (product_id, chunk_type, content, dense_embedding, sparse_embedding)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    records,
                )
    except Exception as e:
        logger.error(f"DATABASE ERROR: {e}")
        raise



# ------------------Retrieval worker functions---------------------------

async def retrieve_and_rerank(
    pool: asyncpg.Pool,
    query: str,
    limit: int = 10,
    top_k: int = 5
) -> list[dict]:
    """
    Standard retrieval pipeline: 
    1. Embed query (dense + sparse)
    2. Hybrid Search (RRF)
    3. Rerank (Cross-Encoder)
    """
    model = get_dense_model()
    sparse_model = get_sparse_model()
    reranker = get_reranker()

    logger.info("embedding_query", query=query)
    
    async with asyncio.TaskGroup() as tg:
        dense_task = tg.create_task(asyncio.to_thread(lambda: next(model.query_embed([query])).tolist()))
        sparse_task = tg.create_task(asyncio.to_thread(lambda: next(sparse_model.query_embed([query]))))

    query_embedding = dense_task.result()
    sparse_embedding_raw = sparse_task.result()

    sparse_query = dict(zip(
        sparse_embedding_raw.indices.tolist(), 
        sparse_embedding_raw.values.tolist()
    ))
    sparse_query = SparseVector(sparse_query, settings.sparse_dimensions)

    logger.info("searching_hybrid")
    candidates = await search_hybrid(
        pool, 
        query_embedding, 
        sparse_query, 
        limit=limit
    )

    logger.info("reranking_start", candidates_count=len(candidates))
    reranked_docs = await rerank_candidates(
        reranker, 
        query, 
        candidates, 
        top_k=top_k
    )
    return reranked_docs



async def search_dense(
    pool: asyncpg.Pool,
    query_embedding: list[float],
    limit: int = 50
) -> list[dict]:
    """Search for similar products using dense vector cosine similarity."""
    rows = await pool.fetch(
        """
        SELECT chunk_id as id, content, 1 - (dense_embedding <=> $1) AS dense_score
        FROM product_chunks
        ORDER BY dense_score DESC
        LIMIT $2
        """,
        query_embedding,
        limit,
    )
    return [dict(row) for row in rows]


async def search_sparse(
    pool: asyncpg.Pool,
    sparse_query: SparseVector | dict[int, float],
    limit: int = 50
) -> list[dict]:
    """Search for similar products using sparse vector similarity."""
    if isinstance(sparse_query, dict):
        sparse_query = SparseVector(sparse_query, settings.sparse_dimensions)
    rows = await pool.fetch(
        """
        SELECT chunk_id as id, content, -(sparse_embedding <#> $1) AS sparse_score
        FROM product_chunks
        ORDER BY sparse_score DESC
        LIMIT $2
        """,
        sparse_query,
        limit,
    )
    return [dict(row) for row in rows]


async def search_hybrid(
    pool: asyncpg.Pool,
    dense_query: list[float],
    sparse_query: SparseVector,
    limit: int = 50,
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[dict]:
    """
    Perform hybrid search using Reciprocal Rank Fusion (RRF).
    Combines dense and sparse vector similarity.
    """
    async with asyncio.TaskGroup() as tg:
        dense_task = tg.create_task(search_dense(pool, dense_query, limit=limit * 2))
        sparse_task = tg.create_task(search_sparse(pool, sparse_query, limit=limit * 2))

    dense_results = dense_task.result()
    sparse_results = sparse_task.result()

    scores = {}  # {id: score}
    metadata = {} # {id: {content: ...}} 

    for rank, res in enumerate(dense_results):
        doc_id = res["id"]
        scores[doc_id] = scores.get(doc_id, 0) + dense_weight / (rank + k)
        if doc_id not in metadata:
            metadata[doc_id] = res
        metadata[doc_id]["dense_score"] = res["dense_score"]

    for rank, res in enumerate(sparse_results):
        doc_id = res["id"]
        scores[doc_id] = scores.get(doc_id, 0) + sparse_weight / (rank + k)
        if doc_id not in metadata:
            metadata[doc_id] = res
        metadata[doc_id]["sparse_score"] = res["sparse_score"]
           

    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    final_results = []
    for doc_id, score in sorted_ids[:limit]:
        res = metadata[doc_id]
        res["hybrid_score"] = score
        final_results.append(res)

    return final_results



async def rerank_candidates(
    reranker: TextCrossEncoder,
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """
    Rerank candidates using a cross-encoder and return the top-K dictionaries.
    """
    if not candidates:
        return []

    documents = [c["content"] for c in candidates]
    scores = await asyncio.to_thread(
        lambda: list(reranker.rerank(query, documents))
    )
    results = [
        {**candidate, "rerank_score": float(score)}
        for candidate, score in zip(candidates, scores)
    ]
    results.sort(key=lambda x: x["rerank_score"], reverse=True)

    return results[:top_k]