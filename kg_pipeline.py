"""
ECG KG-RAG pipeline.

Commands:
  build   - Extract triples from PDFs with MedGemma, build graph
  stats   - Print knowledge graph statistics
  query   - Hybrid KG + vector query from ECG XML
  export  - Export graph to Obsidian vault

Usage:
  python kg_pipeline.py build [--model google/medgemma-4b-it] [--resume]
  python kg_pipeline.py stats
  python kg_pipeline.py query path/to/ecg.xml [--top-k 5] [--lang ko] [--hops 2]
  python kg_pipeline.py export [--vault ./obsidian_vault]
"""

import argparse
import json
import unicodedata
from pathlib import Path

from config import BOOK_META, DATA_DIR, KG_MODEL_ID, KG_TRIPLES_RAW_PATH


def build(model_id: str = KG_MODEL_ID, resume: bool = False, pdf_dir: Path = DATA_DIR) -> None:
    from src.ingest.chunker import chunk_pages
    from src.ingest.pdf_extractor import extract_pages
    from src.kg.extractor import extract_triples, load_model
    from src.kg.graph_store import add_triple, graph_stats, load_graph, save_graph

    KG_TRIPLES_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    processed_keys: set[str] = set()
    if resume and KG_TRIPLES_RAW_PATH.exists():
        with KG_TRIPLES_RAW_PATH.open() as f:
            for line in f:
                rec = json.loads(line)
                if "_chunk_key" in rec:
                    processed_keys.add(rec["_chunk_key"])
        print(f"Resume mode: {len(processed_keys)} chunks already processed")

    model, tokenizer = load_model(model_id)

    import networkx as nx
    g = load_graph() if resume else nx.DiGraph()

    raw_fp = KG_TRIPLES_RAW_PATH.open("a" if resume else "w")
    total_triples = 0

    pdf_files = list(pdf_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF(s)")

    for pdf_path in pdf_files:
        normalized_name = unicodedata.normalize("NFC", pdf_path.name)
        book_meta = BOOK_META.get(normalized_name)
        if book_meta is None:
            print(f"  [skip] {pdf_path.name}")
            continue

        print(f"  Processing: {pdf_path.name} ...", flush=True)
        pages = list(extract_pages(pdf_path))
        chunks = list(chunk_pages(pages, book_meta))
        book_triples = 0

        for i, chunk in enumerate(chunks):
            chunk_key = f"{book_meta['source_book']}:{chunk.get('page_num')}:{i}"
            if chunk_key in processed_keys:
                continue

            triples = extract_triples(
                model, tokenizer,
                text=chunk["content"],
                source_meta={
                    "source_book": book_meta["source_book"],
                    "page_num": chunk.get("page_num"),
                },
            )
            for t in triples:
                add_triple(g, t)
                raw_fp.write(json.dumps({**t, "_chunk_key": chunk_key}, ensure_ascii=False) + "\n")

            book_triples += len(triples)
            total_triples += len(triples)

            if (i + 1) % 50 == 0:
                save_graph(g)
                raw_fp.flush()
                print(f"    [{i+1}/{len(chunks)}] {total_triples} triples so far")

        print(f"    Done: {book_triples} triples from {len(chunks)} chunks")

    raw_fp.close()
    save_graph(g)

    s = graph_stats(g)
    print(f"\nBuild complete: {s['nodes']} nodes, {s['edges']} edges, {total_triples} raw triples")


def stats_cmd() -> None:
    from src.kg.graph_store import graph_stats, load_graph
    g = load_graph()
    if g.number_of_nodes() == 0:
        print("Graph is empty. Run: python kg_pipeline.py build")
        return
    s = graph_stats(g)
    print(f"Nodes : {s['nodes']}")
    print(f"Edges : {s['edges']}")
    print("\nNode types:")
    for t, c in sorted(s["node_types"].items(), key=lambda x: -x[1]):
        print(f"  {t:20s} {c}")
    print("\nRelation types:")
    for r, c in sorted(s["relation_types"].items(), key=lambda x: -x[1]):
        print(f"  {r:30s} {c}")


def query_cmd(
    xml_source: str,
    top_k: int = 5,
    language: str | None = None,
    audience_level: str | None = None,
    kg_hops: int = 2,
) -> None:
    from src.kg.kg_retriever import format_hybrid_context, kg_retrieve
    from src.query.xml_parser import parse_xml
    ctx = parse_xml(xml_source)
    print("=== ECG Query Context ===")
    print(f"  Diagnoses:       {ctx.diagnoses}")
    print(f"  Findings:        {ctx.findings}")
    print(f"  Query:           {ctx.natural_query}")
    print()

    result = kg_retrieve(
        ctx, top_k=top_k, language=language,
        audience_level=audience_level, kg_hops=kg_hops,
    )
    print(f"  Linked entities: {result['linked_entities']}")
    print()
    print(format_hybrid_context(result))


def export_cmd(vault_path: Path) -> None:
    from src.kg.graph_store import load_graph
    from src.kg.obsidian_export import export_to_obsidian
    g = load_graph()
    if g.number_of_nodes() == 0:
        print("Graph is empty. Run: python kg_pipeline.py build")
        return
    n = export_to_obsidian(g, vault_path)
    print(f"Exported {n} notes to {vault_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ECG KG-RAG pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    bp = sub.add_parser("build", help="Extract triples with MedGemma")
    bp.add_argument("--model", default=KG_MODEL_ID)
    bp.add_argument("--resume", action="store_true")
    bp.add_argument("--data-dir", default=str(DATA_DIR))

    sub.add_parser("stats", help="Print graph statistics")

    qp = sub.add_parser("query", help="KG + vector hybrid query")
    qp.add_argument("xml_path", nargs="?")
    qp.add_argument("--xml")
    qp.add_argument("--top-k", type=int, default=5)
    qp.add_argument("--lang", choices=["en", "ko"], default=None)
    qp.add_argument("--level", choices=["basic", "clinical", "specialist"], default=None)
    qp.add_argument("--hops", type=int, default=2)

    ep = sub.add_parser("export", help="Export graph to Obsidian vault")
    ep.add_argument("--vault", default="./obsidian_vault")

    args = parser.parse_args()

    if args.command == "build":
        build(model_id=args.model, resume=args.resume, pdf_dir=Path(args.data_dir))
    elif args.command == "stats":
        stats_cmd()
    elif args.command == "query":
        if args.xml:
            xml_source = args.xml
        elif args.xml_path:
            xml_source = args.xml_path
        else:
            parser.error("Provide xml_path or --xml")
        query_cmd(xml_source, top_k=args.top_k, language=args.lang,
                  audience_level=args.level, kg_hops=args.hops)
    elif args.command == "export":
        export_cmd(Path(args.vault))


if __name__ == "__main__":
    main()
