
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from semantic_text_splitter import TextSplitter

from core.logging import get_logger

logger = get_logger(__name__)

# ── Local Model Cache ────────────────────────────────────────
CACHE_DIR = "models/fastembed/"

# ── Dense model singleton ────────────────────────────────────
_model: TextEmbedding | None = None
MODEL_NAME = "BAAI/bge-small-en-v1.5"
splitter = TextSplitter(capacity=1200,overlap=100)


def load_dense_model() -> TextEmbedding:
    """Load and cache the dense TextEmbedding model.

    Safe to call multiple times — returns the cached instance
    after the first load.
    """
    global _model
    if _model is not None:
        logger.info("model_already_loaded")
        return _model

    logger.info("model_load_start")
    _model = TextEmbedding(MODEL_NAME, threads=1, cache_dir=CACHE_DIR)
    logger.info("model_load_complete")
    return _model


def get_dense_model() -> TextEmbedding:
    """Return the cached model; loads if not yet loaded."""
    global _model
    if _model is None:
        return load_dense_model()
    return _model


def unload_model():
    """Unload the dense embedding model."""
    global _model
    if _model is not None:
        logger.info("model_unload_start")
        del _model
        _model = None
        import gc
        gc.collect()
        logger.info("model_unload_complete")




# ── Sparse model singleton ────────────────────────────────────
_sparse_model: SparseTextEmbedding | None = None
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"


def load_sparse_model() -> SparseTextEmbedding:
    """Load and cache the SPLADE SparseTextEmbedding model."""
    global _sparse_model
    if _sparse_model is not None:
        logger.info("sparse_model_already_loaded")
        return _sparse_model

    logger.info("sparse_model_load_start")
    _sparse_model = SparseTextEmbedding(SPARSE_MODEL_NAME, threads=1, cache_dir=CACHE_DIR)
    logger.info("sparse_model_load_complete")
    return _sparse_model


def get_sparse_model() -> SparseTextEmbedding:
    """Return the cached sparse model; loads if not yet loaded."""
    global _sparse_model
    if _sparse_model is None:
        return load_sparse_model()
    return _sparse_model


def unload_sparse_model():
    """Unload the sparse embedding model."""
    global _sparse_model
    if _sparse_model is not None:
        logger.info("sparse_model_unload_start")
        del _sparse_model
        _sparse_model = None
        import gc
        gc.collect()
        logger.info("sparse_model_unload_complete")





# ── Reranker singleton ──────────────────────────────────────
_reranker: TextCrossEncoder | None = None
RERANKER_MODEL_NAME = "jinaai/jina-reranker-v1-turbo-en"


def load_reranker_model() -> TextCrossEncoder:
    """Load and cache the cross-encoder reranker model."""
    global _reranker
    if _reranker is not None:
        logger.info("reranker_already_loaded")
        return _reranker

    logger.info("reranker_load_start")
    _reranker = TextCrossEncoder(RERANKER_MODEL_NAME, cache_dir=CACHE_DIR)
    logger.info("reranker_load_complete")
    return _reranker


def get_reranker() -> TextCrossEncoder:
    """Return the cached reranker; loads if not yet loaded."""
    global _reranker
    if _reranker is None:
        return load_reranker_model()
    return _reranker


def unload_reranker_model():
    """Unload the reranker model."""
    global _reranker
    if _reranker is not None:
        logger.info("reranker_unload_start")
        del _reranker
        _reranker = None
        import gc
        gc.collect()
        logger.info("reranker_unload_complete")



# ── Helpers ──────────────────────────────────────────────────

def _is_empty(value) -> bool:
    """Return True if value is None, empty, or a CSV null string."""
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in ("null", "none", "n/a", "na", "nan")


def chunk_product(product: dict) -> list[tuple[str, str]]:
    """
    Splits a product into logical chunks for individual embedding.
    Returns a list of (chunk_type, content) tuples.
    Skips any content column that is null or empty.
    """
    chunks = []
    
    # 1. Metadata Chunk (Small, fast to search)
    power = "Not Available" if _is_empty(product.get("power_consumption")) else product.get("power_consumption")
        
    metadata_fields = [
        ("SKU", product.get("sku")),
        ("Product Type", product.get("product_type")),
        ("Power Consumption", power),
    ]
    metadata_text = "\n".join(f"{k}: {v}" for k, v in metadata_fields if v)

    # 2. Specifications Chunk
    spec_text = product.get("key_spec")
    if not _is_empty(spec_text):
        spec_chunks = splitter.chunks(spec_text)
        for chunk in spec_chunks:
            chunks.append(("specifications", metadata_text + "\n" + f"Key Specifications: {chunk}"))

    # 3. Description Chunk
    desc_text = product.get("item_description")
    if not _is_empty(desc_text):
        description_chunks = splitter.chunks(desc_text)
        for chunk in description_chunks:
            chunks.append(("description", metadata_text + "\n" + f"Description: {chunk}"))
    
    # 4. Feature Enhancement Chunk
    feature_enhancement_text = product.get("feature_enhancement")
    if not _is_empty(feature_enhancement_text):
        fe_chunks = splitter.chunks(feature_enhancement_text)
        for chunk in fe_chunks:
            chunks.append(("feature_enhancement", metadata_text + "\n" + f"Feature Enhancement: {chunk}"))

    return chunks







