
from broker import rag_broker
from services.rag_pipeline import retrieve_and_rerank
from services.llm import stream_rag_response
from core.logging import get_logger
from taskiq import Context, TaskiqDepends

from utils.search_product import get_eol_info

logger = get_logger(__name__)

@rag_broker.task(retry_on_error=True, max_retries=3)
async def rag_retrieve_task(
    query: str,
    context: Context = TaskiqDepends()
) -> dict:
    """
    Standard retrieval-only task.
    Returns the top-5 chunks as a JSON result.
    """
    logger.info("rag_retrieve_task_start", query=query)
    try:
        pool = context.state.db.get_pool()
        reranked_docs= await retrieve_and_rerank(pool, query, top_k=5)
        eol_info = await get_eol_info([doc["content"] for doc in reranked_docs])
        chunks = [
            {
                "content": doc["content"],
                "dense_score": doc.get("dense_score"),
                "sparse_score": doc.get("sparse_score"),
                "rerank_score": doc.get("rerank_score"),
                "hybrid_score": doc.get("hybrid_score"),
            }
            for doc in reranked_docs
        ]

        logger.info("rag_retrieve_task_complete", chunks_returned=len(chunks))
        return {"status": "success",
                "query": query, 
                "chunks": chunks,
                "eol_status": eol_info}

    except Exception as e:
        logger.exception("rag_retrieve_task_failed", error=str(e))
        return {"status": "error", "message": str(e)}


@rag_broker.task(retry_on_error=True, max_retries=3)
async def rag_query_task(
    query: str, 
    context: Context = TaskiqDepends()
) -> dict:
    """
    Full RAG task: Retrieval + LLM response streaming via Redis PubSub.
    """
    logger.info("rag_query_task_start", query=query)
    try:
        pool = context.state.db.get_pool()
        reranked_docs= await retrieve_and_rerank(pool, query, top_k=5, limit=10)
        logger.info("generation_start")
        retrieved_context = "\n---\n".join(c["content"] for c in reranked_docs)

        final_answer = []
        async for token in stream_rag_response(
            query, 
            retrieved_context, 
            [doc["content"] for doc in reranked_docs],
            task_id=context.message.task_id
        ):
            final_answer.append(token)
            print(token, end="", flush=True)

        answer_text = "".join(final_answer)

        logger.info("rag_query_task_complete", answer_length=len(answer_text))
        return {
            "status": "success",
            "query": query,
            "answer": answer_text
        }
    except Exception as e:
        logger.exception("rag_query_task_failed", error=str(e))
        raise
