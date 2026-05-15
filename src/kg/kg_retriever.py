"""Hybrid KG + vector retrieval for ECG RAG queries."""

import difflib

import networkx as nx

from src.kg.graph_store import get_subgraph_context, load_graph
from src.query.retriever import format_context, retrieve
from src.query.xml_parser import ECGQueryContext


def _entity_link(g: nx.DiGraph, name: str, cutoff: float = 0.7) -> str | None:
    """Exact match first, then fuzzy match against node labels."""
    key = name.strip().lower()
    if key in g:
        return key
    labels = {data.get("label", k).lower(): k for k, data in g.nodes(data=True)}
    matches = difflib.get_close_matches(key, labels.keys(), n=1, cutoff=cutoff)
    return labels[matches[0]] if matches else None


def kg_retrieve(
    ctx: ECGQueryContext,
    top_k: int = 5,
    language: str | None = None,
    audience_level: str | None = None,
    kg_hops: int = 2,
) -> dict:
    """
    Hybrid retrieval: graph neighborhood + vector search.
    Returns:
        {kg_context: str, vector_results: list, linked_entities: list}
    """
    g = load_graph()

    candidates = ctx.diagnoses + ctx.findings
    linked: list[str] = []
    for candidate in candidates:
        node_key = _entity_link(g, candidate)
        if node_key is not None:
            label = g.nodes[node_key].get("label", candidate)
            linked.append(label)

    kg_context = get_subgraph_context(g, linked, hops=kg_hops) if linked else ""
    vector_results = retrieve(ctx, top_k=top_k, language=language, audience_level=audience_level)

    return {
        "kg_context": kg_context,
        "vector_results": vector_results,
        "linked_entities": linked,
    }


def format_hybrid_context(result: dict) -> str:
    parts = []
    if result["linked_entities"]:
        parts.append(
            f"=== Knowledge Graph Context (entities: {', '.join(result['linked_entities'])}) ==="
        )
        parts.append(result["kg_context"])
        parts.append("")
    if result["vector_results"]:
        parts.append("=== Retrieved Passages ===")
        parts.append(format_context(result["vector_results"]))
    return "\n".join(parts)
