"""Qdrant local collection: create, upsert, and hybrid search."""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from config import COLLECTION_NAME, EMBEDDING_DIM, HYBRID_ENABLED, QDRANT_PATH


_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        QDRANT_PATH.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(QDRANT_PATH))
    return _client


def drop_collection(client: QdrantClient) -> None:
    """Delete the collection if it exists."""
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        sparse_cfg = (
            {"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))}
            if HYBRID_ENABLED else {}
        )
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)},
            sparse_vectors_config=sparse_cfg,
        )
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
    """Bulk-upsert embedded chunks. Each chunk must have 'id', 'embedding',
    and (when HYBRID_ENABLED) 'sparse_indices' + 'sparse_values'."""
    payload_exclude = {"id", "embedding", "sparse_indices", "sparse_values"}
    points = []
    for c in chunks:
        vector: dict = {"dense": c["embedding"]}
        if HYBRID_ENABLED and c.get("sparse_indices"):
            vector["sparse"] = SparseVector(
                indices=c["sparse_indices"],
                values=c["sparse_values"],
            )
        points.append(
            PointStruct(
                id=c["id"],
                vector=vector,
                payload={k: v for k, v in c.items() if k not in payload_exclude},
            )
        )
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def search(
    client: QdrantClient,
    query_vector: list[float],
    query_sparse: tuple[list[int], list[float]] | None = None,
    top_k: int = 5,
    audience_level: str | None = None,
    language: str | None = None,
    content_type: str | None = None,
) -> list[dict]:
    """
    Hybrid search (dense + sparse RRF) when HYBRID_ENABLED and query_sparse
    is provided; falls back to dense-only otherwise.
    """
    must = []
    if audience_level:
        must.append(FieldCondition(key="audience_level", match=MatchValue(value=audience_level)))
    if language:
        must.append(FieldCondition(key="language", match=MatchValue(value=language)))
    if content_type:
        must.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
    query_filter = Filter(must=must) if must else None

    if HYBRID_ENABLED and query_sparse is not None:
        sparse_indices, sparse_values = query_sparse
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(query=query_vector, using="dense", limit=top_k * 3),
                Prefetch(
                    query=SparseVector(indices=sparse_indices, values=sparse_values),
                    using="sparse",
                    limit=top_k * 3,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
    else:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            using="dense",
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
