"""BGE-M3 dense embeddings with batched inference.

Pinned to cuda:0 so FlagEmbedding uses single-device mode — avoids
the multi-GPU spawn that produces empty sub-batches and crashes.
"""

from typing import Iterator
import numpy as np
from FlagEmbedding import BGEM3FlagModel

_model: BGEM3FlagModel | None = None


def _get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["cuda:0"])
    return _model


def embed_chunks(
    chunks: list[dict],
    batch_size: int = 16,
) -> Iterator[dict]:
    """
    Adds 'embedding' (list[float]) to each chunk dict and yields it.
    Skips chunks with empty content to prevent tokenizer errors.
    """
    model = _get_model()

    valid = [c for c in chunks if c.get("content", "").strip()]

    for i in range(0, len(valid), batch_size):
        batch = valid[i : i + batch_size]
        texts = [c["content"] for c in batch]
        result = model.encode(texts, batch_size=batch_size, max_length=512)
        dense_vecs: np.ndarray = result["dense_vecs"]

        for chunk, vec in zip(batch, dense_vecs):
            yield {**chunk, "embedding": vec.tolist()}
