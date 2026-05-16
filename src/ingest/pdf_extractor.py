"""PDF → page-level element extraction using PyMuPDF.

Each page yields a list of elements sorted by reading order (y0 → x0):
  {"type": "text",  "content": str,  "bbox": tuple}
  {"type": "table", "markdown": str, "rows": int, "cols": int, "bbox": tuple}
  {"type": "image", "bytes": bytes,  "ext": str, "width": int, "height": int, "bbox": tuple}
"""

from pathlib import Path
from typing import Iterator
import fitz  # PyMuPDF

from config import IMAGE_MIN_HEIGHT, IMAGE_MIN_WIDTH


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_header_footer(bbox: tuple, page_height: float) -> bool:
    _, y0, _, y1 = bbox
    return y1 < page_height * 0.07 or y0 > page_height * 0.93


def _center_in_bbox(block_bbox: tuple, region: tuple) -> bool:
    """True if the center of block_bbox falls inside region."""
    bx0, by0, bx1, by1 = block_bbox
    rx0, ry0, rx1, ry1 = region
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    return rx0 <= cx <= rx1 and ry0 <= cy <= ry1


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    if not rows:
        return ""
    header = [cell or "" for cell in rows[0]]
    separator = ["---"] * len(header)
    body = [[cell or "" for cell in row] for row in rows[1:]]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ── Per-page extraction ───────────────────────────────────────────────────────

def _extract_elements(page: fitz.Page, doc: fitz.Document) -> list[dict]:
    page_height = page.rect.height
    elements: list[dict] = []

    # 1. Tables (collect bboxes first to filter overlapping text blocks)
    table_bboxes: list[tuple] = []
    try:
        finder = page.find_tables()
        for tbl in finder.tables:
            rows = tbl.extract()
            if not rows or len(rows) < 2:
                continue
            markdown = _table_to_markdown(rows)
            if not markdown:
                continue
            bbox = tuple(tbl.bbox)
            table_bboxes.append(bbox)
            elements.append({
                "type": "table",
                "markdown": markdown,
                "rows": len(rows),
                "cols": len(rows[0]) if rows else 0,
                "bbox": bbox,
            })
    except Exception:
        pass

    # 2. Text blocks (skip header/footer and cells inside table regions)
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        bbox = tuple(block["bbox"])
        if _is_header_footer(bbox, page_height):
            continue
        if any(_center_in_bbox(bbox, tr) for tr in table_bboxes):
            continue

        spans: list[str] = []
        for line in block["lines"]:
            parts = [s["text"].strip() for s in line["spans"] if s["text"].strip()]
            if parts:
                spans.append(" ".join(parts))
        content = "\n".join(spans).strip()
        if not content:
            continue
        elements.append({"type": "text", "content": content, "bbox": bbox})

    # 3. Images (filter small/decorative ones; get page bbox via get_image_rects)
    for img_info in page.get_images(full=True):
        xref, _, width, height = img_info[0], img_info[1], img_info[2], img_info[3]
        if width < IMAGE_MIN_WIDTH or height < IMAGE_MIN_HEIGHT:
            continue
        try:
            rects = page.get_image_rects(xref)
            bbox = tuple(rects[0]) if rects else (0.0, 0.0, float(width), float(height))
            img_data = doc.extract_image(xref)
            elements.append({
                "type": "image",
                "bytes": img_data["image"],
                "ext": img_data.get("ext", "png"),
                "width": width,
                "height": height,
                "bbox": bbox,
            })
        except Exception:
            continue

    # Sort by reading order: top-to-bottom, then left-to-right
    elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))
    return elements


def extract_pages(pdf_path: Path) -> Iterator[dict]:
    """
    Yields one dict per page:
      {page_num, elements: list[dict], source_file}

    Elements are sorted by reading order (y0, x0).
    Pages with no elements are skipped.
    """
    doc = fitz.open(str(pdf_path))
    for page in doc:
        elements = _extract_elements(page, doc)
        if not elements:
            continue

        # Require some text content or at least one non-text element
        text_len = sum(len(e.get("content", "")) for e in elements if e["type"] == "text")
        non_text = any(e["type"] in ("table", "image") for e in elements)
        if text_len < 80 and not non_text:
            continue

        yield {
            "page_num": page.number + 1,
            "elements": elements,
            "source_file": pdf_path.name,
        }

    doc.close()
