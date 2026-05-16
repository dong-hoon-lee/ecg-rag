"""BGE-M3 dense + sparse embeddings with batched inference.

Pinned to cuda:0 so FlagEmbedding uses single-device mode — avoids
the multi-GPU spawn that produces empty sub-batches and crashes.

Yields per chunk:
  embedding        — dense vector (list[float], dim=1024)
  sparse_indices   — lexical weight token IDs (list[int])
  sparse_values    — lexical weight scores (list[float])
"""

from typing import Iterator
import numpy as np
from FlagEmbedding import BGEM3FlagModel

from config import HYBRID_ENABLED

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
    Adds 'embedding', 'sparse_indices', 'sparse_values' to each chunk dict.
    Skips chunks with empty content to prevent tokenizer errors.
    """
    model = _get_model()
    valid = [c for c in chunks if c.get("content", "").strip()]

    for i in range(0, len(valid), batch_size):
        batch = valid[i : i + batch_size]
        texts = [c["content"] for c in batch]

        result = model.encode(
            texts,
            batch_size=batch_size,
            max_length=512,
            return_dense=True,
            return_sparse=HYBRID_ENABLED,
        )

        dense_vecs: np.ndarray = result["dense_vecs"]
        sparse_weights: list[dict] = result.get("lexical_weights", [{}] * len(batch))

        for chunk, dvec, sweights in zip(batch, dense_vecs, sparse_weights):
            indices = [int(k) for k in sweights.keys()]
            values = [float(v) for v in sweights.values()]
            yield {
                **chunk,
                "embedding": dvec.tolist(),
                "sparse_indices": indices,
                "sparse_values": values,
            }
