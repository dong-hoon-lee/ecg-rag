"""
ECG RAG Phase 1 pipeline.

Usage:
  # 1. Ingest all PDFs (run once):
  python pipeline.py ingest

  # 2. Query with an ECG XML file:
  python pipeline.py query path/to/ecg.xml [--top-k 5] [--lang ko] [--level clinical]

  # 3. Query with raw XML string (for testing):
  python pipeline.py query --xml '<ECGReport>...'
"""

import argparse
import unicodedata
from pathlib import Path

from config import BOOK_META, DATA_DIR
from src.db.qdrant_store import drop_collection, ensure_collection, get_client, upsert_chunks
from src.ingest.embedder import embed_chunks
from src.ingest.image_describer import describe_images_in_pages
from src.ingest.layout_chunker import chunk_pages
from src.ingest.pdf_extractor import extract_pages
from src.query.retriever import format_context, retrieve
from src.query.xml_parser import parse_xml


def reset_collection() -> None:
    """Drop and recreate the Qdrant collection."""
    client = get_client()
    drop_collection(client)
    ensure_collection(client)
    print(f"Collection '{__import__('config').COLLECTION_NAME}' reset.")


def ingest(pdf_dir: Path = DATA_DIR, reset: bool = False) -> None:
    client = get_client()
    if reset:
        drop_collection(client)
    ensure_collection(client)

    pdf_files = list(pdf_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}")

    for pdf_path in pdf_files:
        # Normalize to NFC: filesystems (esp. macOS-origin files) may store names in NFD
        normalized_name = unicodedata.normalize("NFC", pdf_path.name)
        book_meta = BOOK_META.get(normalized_name)
        if book_meta is None:
            print(f"  [skip] {pdf_path.name} — not in BOOK_META")
            continue

        pages = list(extract_pages(pdf_path))
        n_imgs = sum(1 for p in pages for e in p["elements"] if e["type"] == "image")
        n_tbls = sum(1 for p in pages for e in p["elements"] if e["type"] == "table")
        print(f"  Processing: {pdf_path.name} ({len(pages)}p, {n_imgs} img, {n_tbls} tbl) ...", flush=True)

        print(f"    VLM describing {n_imgs} images (parallel) ...", flush=True)
        describe_images_in_pages(pages)

        print(f"    Chunking + embedding ...", flush=True)
        chunks = list(chunk_pages(pages, book_meta))
        embedded = list(embed_chunks(chunks))
        upsert_chunks(client, embedded)

        n_table = sum(1 for c in chunks if c.get("has_table"))
        n_image = sum(1 for c in chunks if c.get("has_image"))
        print(f"    → {len(chunks)} chunks ({n_table} w/ table, {n_image} w/ image) ingested")

    print("Ingest complete.")


def query(
    xml_source: str,
    top_k: int = 5,
    language: str | None = None,
    audience_level: str | None = None,
) -> None:
    ctx = parse_xml(xml_source)

    print("=== ECG Query Context ===")
    print(f"  Diagnoses:       {ctx.diagnoses}")
    print(f"  Findings:        {ctx.findings}")
    print(f"  Abnormal params: {ctx.abnormal_params}")
    print(f"  Query:           {ctx.natural_query}")
    print()

    results = retrieve(ctx, top_k=top_k, language=language, audience_level=audience_level)
    print("=== Retrieved Context ===")
    print(format_context(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="ECG RAG pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_p = sub.add_parser("ingest", help="Ingest PDFs into Qdrant")
    ingest_p.add_argument("--data-dir", default=str(DATA_DIR))
    ingest_p.add_argument("--reset", action="store_true",
                          help="Drop existing collection before ingesting")

    sub.add_parser("reset", help="Drop and recreate the Qdrant collection")

    query_p = sub.add_parser("query", help="Query with an ECG XML")
    query_p.add_argument("xml_path", nargs="?", help="Path to ECG XML file")
    query_p.add_argument("--xml", help="Raw XML string (overrides xml_path)")
    query_p.add_argument("--top-k", type=int, default=5)
    query_p.add_argument("--lang", choices=["en", "ko"], default=None)
    query_p.add_argument("--level", choices=["basic", "clinical", "specialist"], default=None)

    args = parser.parse_args()

    if args.command == "reset":
        reset_collection()
    elif args.command == "ingest":
        ingest(Path(args.data_dir), reset=args.reset)
    elif args.command == "query":
        if args.xml:
            xml_source = args.xml
        elif args.xml_path:
            xml_source = args.xml_path
        else:
            parser.error("Provide xml_path or --xml")
        query(xml_source, top_k=args.top_k, language=args.lang, audience_level=args.level)


if __name__ == "__main__":
    main()
