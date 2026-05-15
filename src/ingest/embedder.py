"""BGE-M3 dense embeddings with batched inference."""

from typing import Iterator
import numpy as np
from FlagEmbedding import BGEM3FlagModel

_model: BGEM3FlagModel | None = None


def _get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    return _model


def embed_chunks(
    chunks: list[dict],
    batch_size: int = 16,
) -> Iterator[dict]:
    """
    Adds 'embedding' (list[float]) to each chunk dict and yields it.
    Processes in batches to avoid OOM on large corpora.
    """
    model = _get_model()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["content"] for c in batch]
        result = model.encode(texts, batch_size=batch_size, max_length=512)
        dense_vecs: np.ndarray = result["dense_vecs"]

        for chunk, vec in zip(batch, dense_vecs):
            yield {**chunk, "embedding": vec.tolist()}
