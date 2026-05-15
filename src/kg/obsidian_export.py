"""Export the knowledge graph to an Obsidian vault (wikilink markdown)."""

from pathlib import Path

import networkx as nx

from src.kg.graph_store import get_neighbors

_TYPE_DIR = {
    "Diagnosis": "Diagnoses",
    "ECGFinding": "Findings",
    "Parameter": "Parameters",
    "Measurement": "Measurements",
    "Treatment": "Treatments",
    "Drug": "Drugs",
    "Concept": "Concepts",
}

_RELATION_SECTIONS = {
    "has_criteria":        "## Diagnostic Criteria",
    "associated_with":     "## Associated Findings",
    "differentiates_from": "## Differentials",
    "caused_by":           "## Causes",
    "treated_with":        "## Treatment",
    "measured_by":         "## Measured By",
    "indicates":           "## Indicates",
    "excludes":            "## Excludes",
    "normal_range":        "## Normal Range",
    "abnormal_when":       "## Abnormal When",
}


def _safe_filename(label: str) -> str:
    return label.replace("/", "-").replace("\\", "-").replace(":", " -")


def export_to_obsidian(g: nx.DiGraph, vault_path: Path) -> int:
    """
    Write one markdown file per node into vault_path.
    Returns the number of files written.
    """
    vault_path.mkdir(parents=True, exist_ok=True)
    count = 0

    for node_key, data in g.nodes(data=True):
        label = data.get("label", node_key)
        etype = data.get("type", "Concept")
        node_sources = data.get("sources", [])

        subdir = vault_path / _TYPE_DIR.get(etype, "Other")
        subdir.mkdir(exist_ok=True)
        fp = subdir / f"{_safe_filename(label)}.md"

        # Group 1-hop neighbors by relation and direction
        outgoing: dict[str, list[str]] = {}
        incoming: dict[str, list[str]] = {}
        for nb in get_neighbors(g, label, hops=1):
            if nb["distance"] != 1:
                continue
            target = outgoing if nb["direction"] == "outgoing" else incoming
            for rel in nb["relations"]:
                target.setdefault(rel, []).append(nb["label"])

        lines = [f"# {label}", "", f"**Type:** {etype}", ""]

        for rel, section_header in _RELATION_SECTIONS.items():
            targets = outgoing.get(rel, [])
            if targets:
                lines.append(section_header)
                for t in targets:
                    lines.append(f"- [[{t}]]")
                lines.append("")

        if incoming:
            lines.append("## Referenced By")
            for rel, refs in incoming.items():
                for ref in refs:
                    lines.append(f"- [[{ref}]] ({rel})")
            lines.append("")

        if node_sources:
            lines.append("## Sources")
            seen: set[tuple] = set()
            for s in node_sources:
                key = (s.get("source_book", ""), s.get("page_num"))
                if key not in seen:
                    seen.add(key)
                    page = f", p.{s['page_num']}" if s.get("page_num") else ""
                    lines.append(f"- {s.get('source_book', 'unknown')}{page}")
            lines.append("")

        fp.write_text("\n".join(lines), encoding="utf-8")
        count += 1

    return count
