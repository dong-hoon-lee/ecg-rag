"""High-level retrieval: XML context → embedded query → Qdrant search."""

from src.db.qdrant_store import get_client, search
from src.ingest.embedder import embed_chunks
from src.query.xml_parser import ECGQueryContext


def retrieve(
    ctx: ECGQueryContext,
    top_k: int = 5,
    audience_level: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """
    Embed the natural query from ctx and search Qdrant.
    Returns top_k results sorted by cosine similarity score.
    """
    query_chunk = [{"id": "query", "content": ctx.natural_query}]
    embedded = list(embed_chunks(query_chunk, batch_size=1))
    query_vector = embedded[0]["embedding"]

    client = get_client()
    return search(
        client,
        query_vector=query_vector,
        top_k=top_k,
        audience_level=audience_level,
        language=language,
    )


def format_context(results: list[dict]) -> str:
    """Format retrieved chunks into a single LLM context string."""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"[Source {i}: {r['source_book']}, p.{r['page_num']} "
            f"(score={r['score']:.3f})]\n{r['content']}"
        )
    return "\n\n---\n\n".join(parts)
