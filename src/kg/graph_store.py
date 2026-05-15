"""NetworkX knowledge graph with JSON persistence."""

import json
from collections import Counter

import networkx as nx

from config import KG_GRAPH_PATH


def _node_key(name: str) -> str:
    return name.strip().lower()


def load_graph() -> nx.DiGraph:
    KG_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KG_GRAPH_PATH.exists():
        return nx.DiGraph()
    with KG_GRAPH_PATH.open() as f:
        data = json.load(f)
    return nx.node_link_graph(data, directed=True, multigraph=False)


def save_graph(g: nx.DiGraph) -> None:
    KG_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with KG_GRAPH_PATH.open("w") as f:
        json.dump(nx.node_link_data(g), f, ensure_ascii=False, indent=2)


def add_triple(g: nx.DiGraph, triple: dict) -> None:
    """
    Upsert triple into graph.
    Nodes: {label, type, sources: [{source_book, page_num}]}
    Edges: {relations: [{relation, source_book, page_num}]}
    """
    h_key = _node_key(triple["head"])
    t_key = _node_key(triple["tail"])
    source = {"source_book": triple.get("source_book", ""), "page_num": triple.get("page_num")}

    for key, label, etype in [
        (h_key, triple["head"], triple["head_type"]),
        (t_key, triple["tail"], triple["tail_type"]),
    ]:
        if key not in g:
            g.add_node(key, label=label, type=etype, sources=[source])
        elif source not in g.nodes[key]["sources"]:
            g.nodes[key]["sources"].append(source)

    rel_entry = {"relation": triple["relation"], **source}
    if g.has_edge(h_key, t_key):
        if rel_entry not in g.edges[h_key, t_key]["relations"]:
            g.edges[h_key, t_key]["relations"].append(rel_entry)
    else:
        g.add_edge(h_key, t_key, relations=[rel_entry])


def get_neighbors(g: nx.DiGraph, entity: str, hops: int = 2) -> list[dict]:
    """
    BFS up to `hops` in both directions.
    Each result: {node, label, type, relations, direction, distance}
    """
    key = _node_key(entity)
    if key not in g:
        return []

    results = []
    visited = {key}
    frontier = [(key, 0)]

    while frontier:
        current, depth = frontier.pop(0)
        if depth >= hops:
            continue

        for neighbor in g.successors(current):
            if neighbor not in visited:
                visited.add(neighbor)
                rels = [r["relation"] for r in g.edges[current, neighbor]["relations"]]
                results.append({
                    "node": neighbor,
                    "label": g.nodes[neighbor].get("label", neighbor),
                    "type": g.nodes[neighbor].get("type", ""),
                    "relations": rels,
                    "direction": "outgoing",
                    "distance": depth + 1,
                })
                frontier.append((neighbor, depth + 1))

        for neighbor in g.predecessors(current):
            if neighbor not in visited:
                visited.add(neighbor)
                rels = [r["relation"] for r in g.edges[neighbor, current]["relations"]]
                results.append({
                    "node": neighbor,
                    "label": g.nodes[neighbor].get("label", neighbor),
                    "type": g.nodes[neighbor].get("type", ""),
                    "relations": rels,
                    "direction": "incoming",
                    "distance": depth + 1,
                })
                frontier.append((neighbor, depth + 1))

    return results


def get_subgraph_context(g: nx.DiGraph, entities: list[str], hops: int = 2) -> str:
    """Format N-hop neighborhood of entities as text for LLM context."""
    lines = []
    seen_edges: set[tuple] = set()

    for entity in entities:
        key = _node_key(entity)
        if key not in g:
            continue
        label = g.nodes[key].get("label", entity)
        etype = g.nodes[key].get("type", "")
        lines.append(f"[{etype}] {label}")

        for nb in get_neighbors(g, entity, hops=hops):
            for rel in nb["relations"]:
                if nb["direction"] == "outgoing":
                    edge = (label, rel, nb["label"])
                else:
                    edge = (nb["label"], rel, label)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    lines.append(f"  {edge[0]}  --[{edge[1]}]-->  {edge[2]}")

    return "\n".join(lines) if lines else ""


def graph_stats(g: nx.DiGraph) -> dict:
    type_counts = Counter(d.get("type", "Unknown") for _, d in g.nodes(data=True))
    rel_counts: Counter = Counter()
    for _, _, d in g.edges(data=True):
        for r in d.get("relations", []):
            rel_counts[r["relation"]] += 1
    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "node_types": dict(type_counts),
        "relation_types": dict(rel_counts),
    }
