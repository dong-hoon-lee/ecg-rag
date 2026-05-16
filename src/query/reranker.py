"""Cross-encoder re-ranking with BAAI/bge-reranker-v2-m3.

Takes the initial dense-retrieval candidates and re-scores each
(query, document) pair with a cross-encoder, then returns the
top-k highest-scoring results.
"""

from FlagEmbedding import FlagReranker

from config import RERANKER_MODEL

_reranker: FlagReranker | None = None


def _get_reranker() -> FlagReranker:
    global _reranker
    if _reranker is None:
        _reranker = FlagReranker(RERANKER_MODEL, use_fp16=True)
    return _reranker


def rerank(query: str, results: list[dict], top_k: int) -> list[dict]:
    """
    Re-score `results` using the cross-encoder and return the top_k
    highest-scoring items sorted by rerank_score descending.

    Each result dict gets a 'rerank_score' field added.
    Original 'score' (dense cosine) is preserved.
    """
    if not results:
        return results

    reranker = _get_reranker()
    pairs = [[query, r["content"]] for r in results]
    scores: list[float] = reranker.compute_score(pairs, normalize=True)

    for result, score in zip(results, scores):
        result["rerank_score"] = score

    reranked = sorted(results, key=lambda r: r["rerank_score"], reverse=True)
    return reranked[:top_k]
