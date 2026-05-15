"""Qdrant local collection: create, upsert, and search."""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Query,
    VectorParams,
)

from config import COLLECTION_NAME, EMBEDDING_DIM, QDRANT_PATH


_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        QDRANT_PATH.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(QDRANT_PATH))
    return _client


def ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        # Payload indexes only work on server-mode Qdrant; silently skip for local mode
        try:
            for field in ("source_book", "language", "audience_level", "content_type"):
                client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field,
                    field_schema="keyword",
                )
        except Exception:
            pass


def upsert_chunks(client: QdrantClient, chunks: list[dict]) -> None:
    """Bulk-upsert embedded chunks. Each chunk must have 'id' and 'embedding'."""
    points = [
        PointStruct(
            id=c["id"],
            vector=c["embedding"],
            payload={k: v for k, v in c.items() if k not in ("id", "embedding")},
        )
        for c in chunks
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def search(
    client: QdrantClient,
    query_vector: list[float],
    top_k: int = 5,
    audience_level: str | None = None,
    language: str | None = None,
    content_type: str | None = None,
) -> list[dict]:
    """
    Dense cosine similarity search with optional metadata filters.
    Returns list of {score, content, metadata} dicts.
    """
    must = []
    if audience_level:
        must.append(FieldCondition(key="audience_level", match=MatchValue(value=audience_level)))
    if language:
        must.append(FieldCondition(key="language", match=MatchValue(value=language)))
    if content_type:
        must.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))

    query_filter = Filter(must=must) if must else None

    # qdrant-client >= 1.14 uses query_points instead of search
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "score": hit.score,
            "content": hit.payload.get("content", ""),
            "source_book": hit.payload.get("source_book", ""),
            "page_num": hit.payload.get("page_num"),
            "content_type": hit.payload.get("content_type", ""),
            "audience_level": hit.payload.get("audience_level", ""),
            "language": hit.payload.get("language", ""),
        }
        for hit in response.points
    ]
