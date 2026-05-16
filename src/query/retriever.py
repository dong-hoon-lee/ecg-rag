"""High-level retrieval: XML context → embed → hybrid search → rerank."""

from src.db.qdrant_store import get_client, search
from src.ingest.embedder import embed_chunks
from src.query.reranker import rerank
from src.query.xml_parser import ECGQueryContext
from config import HYBRID_ENABLED, RERANKER_ENABLED, RETRIEVAL_TOP_K, RERANK_TOP_K


def retrieve(
    ctx: ECGQueryContext,
    top_k: int = RERANK_TOP_K,
    audience_level: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """
    1. Embed the natural query (dense + sparse).
    2. Hybrid search Qdrant with RRF fusion (or dense-only if HYBRID_ENABLED=False).
    3. Re-rank candidates with cross-encoder and return top_k.
    """
    query_chunk = [{"id": "query", "content": ctx.natural_query}]
    embedded = list(embed_chunks(query_chunk, batch_size=1))
    eq = embedded[0]

    query_sparse = (
        (eq["sparse_indices"], eq["sparse_values"])
        if HYBRID_ENABLED and eq.get("sparse_indices")
        else None
    )

    client = get_client()
    candidates = search(
        client,
        query_vector=eq["embedding"],
        query_sparse=query_sparse,
        top_k=RETRIEVAL_TOP_K if RERANKER_ENABLED else top_k,
        audience_level=audience_level,
        language=language,
    )

    if RERANKER_ENABLED:
        return rerank(ctx.natural_query, candidates, top_k=top_k)
    return candidates


def format_context(results: list[dict]) -> str:
    """Format retrieved chunks into a single LLM context string."""
    parts = []
    for i, r in enumerate(results, 1):
        score_info = f"score={r['score']:.3f}"
        if "rerank_score" in r:
            score_info += f", rerank={r['rerank_score']:.3f}"
        parts.append(
            f"[Source {i}: {r['source_book']}, p.{r['page_num']} ({score_info})]\n{r['content']}"
        )
    return "\n\n---\n\n".join(parts)
