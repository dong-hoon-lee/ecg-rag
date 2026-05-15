"""PDF → page-level text extraction using PyMuPDF."""

from pathlib import Path
from typing import Iterator
import fitz  # PyMuPDF


def _is_header_footer(block: dict, page_height: float) -> bool:
    """Heuristic: blocks in top 7% or bottom 7% of page are likely header/footer."""
    y0, y1 = block["bbox"][1], block["bbox"][3]
    return y1 < page_height * 0.07 or y0 > page_height * 0.93


def extract_pages(pdf_path: Path) -> Iterator[dict]:
    """
    Yields one dict per page:
      {page_num, text, source_file}

    Skips pages with fewer than 80 characters (image-only or blank).
    Filters header/footer blocks heuristically.
    """
    doc = fitz.open(str(pdf_path))
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        page_height = page.rect.height

        lines = []
        for block in blocks:
            if block["type"] != 0:  # 0 = text block
                continue
            if _is_header_footer(block, page_height):
                continue
            for line in block["lines"]:
                spans = [s["text"].strip() for s in line["spans"] if s["text"].strip()]
                if spans:
                    lines.append(" ".join(spans))

        text = "\n".join(lines).strip()
        if len(text) < 80:
            continue

        yield {
            "page_num": page.number + 1,
            "text": text,
            "source_file": pdf_path.name,
        }

    doc.close()
