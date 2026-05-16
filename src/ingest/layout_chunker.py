"""Layout-aware chunking for ECG textbook pages.

Processes elements in reading order (text / table / image) and groups them
into semantically coherent chunks. A new chunk is started when:
  1. A section heading is detected in a text element.
  2. The accumulated token budget exceeds CHUNK_TARGET_TOKENS (narrative)
     or CHUNK_MAX_TOKENS (while inside a criteria block).

Tables and image descriptions are embedded inline into the chunk content
alongside their surrounding text, preserving the original layout context.
"""

import re
import uuid
from typing import Iterator

from config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_SENTENCES, CHUNK_TARGET_TOKENS


# ── Heading / criteria detection ──────────────────────────────────────────────

_HEADING_PATTERNS = [
    re.compile(r"^(chapter|section|part)\b", re.I),
    re.compile(r"^\d+[\.\s]+[A-Z]"),
    re.compile(r"^[IVX]+\.\s+[A-Z]"),
    re.compile(r"^[A-Z][A-Z\s]{4,}$"),
    re.compile(r"^[가-힣]{2,10}\s*([:：]|$)"),
]

_CRITERIA_MARKERS = re.compile(
    r"(\d+\s*(ms|mm|mv|bpm|sec|s\b)|criteria|findings?:|"
    r"characterized by|diagnostic|定義|기준|소견)",
    re.I,
)
_LIST_MARKER = re.compile(r"^\s*([•·\-\*]|\d+[.)]\s)")
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z가-힣])")


def _is_heading(text: str) -> bool:
    s = text.strip()
    if len(s) > 120:
        return False
    return any(p.match(s) for p in _HEADING_PATTERNS)


def _looks_like_criteria(text: str) -> bool:
    return bool(_CRITERIA_MARKERS.search(text) or _LIST_MARKER.match(text))


def _approx_tokens(text: str) -> int:
    return int(len(text.split()) / 0.75)


def _split_sentences(text: str) -> list[str]:
    sentences = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        sentences.extend(p.strip() for p in _SENT_END.split(line) if p.strip())
    return sentences


# ── Bucket (in-progress chunk) ────────────────────────────────────────────────

class _Bucket:
    """Accumulates elements (text sentences / table markdown / image descriptions)."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.tail_sentences: list[str] = []  # last N text sentences for overlap
        self.has_table: bool = False
        self.has_image: bool = False
        self.in_criteria: bool = False
        self.start_page: int | None = None

    def add_text_sentence(self, sent: str, page_num: int) -> None:
        if self.start_page is None:
            self.start_page = page_num
        self.parts.append(sent)
        self.tail_sentences.append(sent)
        if len(self.tail_sentences) > CHUNK_OVERLAP_SENTENCES * 3:
            self.tail_sentences.pop(0)

    def add_table(self, markdown: str, page_num: int) -> None:
        if self.start_page is None:
            self.start_page = page_num
        self.parts.append(f"\n[Table]\n{markdown}\n")
        self.has_table = True

    def add_image(self, description: str, page_num: int) -> None:
        if self.start_page is None:
            self.start_page = page_num
        self.parts.append(f"\n[Figure]\n{description}\n")
        self.has_image = True

    @property
    def content(self) -> str:
        return " ".join(self.parts).strip()

    @property
    def token_count(self) -> int:
        return _approx_tokens(self.content)

    def is_empty(self) -> bool:
        return not self.parts

    def overlap_seed(self) -> list[str]:
        return self.tail_sentences[-CHUNK_OVERLAP_SENTENCES:]


def _flush(bucket: "_Bucket", source_file: str, book_meta: dict) -> dict:
    if bucket.has_table and bucket.has_image:
        ctype = "multimodal"
    elif bucket.has_table:
        ctype = "table"
    elif bucket.has_image:
        ctype = "image_description"
    elif bucket.in_criteria:
        ctype = "criteria"
    else:
        ctype = "narrative"

    return {
        "id": str(uuid.uuid4()),
        "content": bucket.content,
        "content_type": ctype,
        "has_table": bucket.has_table,
        "has_image": bucket.has_image,
        "page_num": bucket.start_page,
        "source_file": source_file,
        **book_meta,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def chunk_pages(pages: list[dict], book_meta: dict) -> Iterator[dict]:
    """
    Takes page dicts from pdf_extractor (elements list) and yields chunk dicts.
    Image elements must already have a "description" field (set by image_describer).
    """
    source_file = pages[0]["source_file"] if pages else ""
    bucket = _Bucket()

    for page in pages:
        pnum = page["page_num"]

        for elem in page["elements"]:

            if elem["type"] == "image":
                description = elem.get("description", "")
                if not description:
                    continue
                bucket.add_image(description, pnum)
                if bucket.token_count > CHUNK_MAX_TOKENS:
                    yield _flush(bucket, source_file, book_meta)
                    bucket = _Bucket()

            elif elem["type"] == "table":
                bucket.add_table(elem["markdown"], pnum)
                if bucket.token_count > CHUNK_MAX_TOKENS:
                    yield _flush(bucket, source_file, book_meta)
                    bucket = _Bucket()

            elif elem["type"] == "text":
                for sent in _split_sentences(elem["content"]):
                    is_head = _is_heading(sent)
                    is_crit = _looks_like_criteria(sent)

                    # Heading → flush current bucket, keep overlap
                    if is_head and not bucket.is_empty():
                        overlap = bucket.overlap_seed()
                        yield _flush(bucket, source_file, book_meta)
                        bucket = _Bucket()
                        for s in overlap:
                            bucket.add_text_sentence(s, pnum)

                    # Entering criteria block from narrative
                    if is_crit and not bucket.in_criteria and not bucket.is_empty():
                        if bucket.token_count > 80:
                            overlap = bucket.overlap_seed()
                            yield _flush(bucket, source_file, book_meta)
                            bucket = _Bucket()
                            for s in overlap:
                                bucket.add_text_sentence(s, pnum)
                        bucket.in_criteria = True

                    # Leaving criteria block
                    if not is_crit and bucket.in_criteria and not bucket.is_empty():
                        overlap = bucket.overlap_seed()
                        yield _flush(bucket, source_file, book_meta)
                        bucket = _Bucket()
                        for s in overlap:
                            bucket.add_text_sentence(s, pnum)

                    bucket.add_text_sentence(sent, pnum)

                    limit = CHUNK_MAX_TOKENS if bucket.in_criteria else CHUNK_TARGET_TOKENS
                    if bucket.token_count >= limit:
                        overlap = bucket.overlap_seed()
                        yield _flush(bucket, source_file, book_meta)
                        bucket = _Bucket()
                        for s in overlap:
                            bucket.add_text_sentence(s, pnum)

    if not bucket.is_empty():
        yield _flush(bucket, source_file, book_meta)
