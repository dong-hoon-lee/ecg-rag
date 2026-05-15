"""
Semantic-boundary chunking for ECG textbook pages.

Strategy:
  1. Split text into sentences.
  2. Detect section headings — start a new chunk at each heading.
  3. Detect diagnostic-criteria blocks (bullet lists, numbered lists, lines
     with clinical thresholds like ms/mm/mV/bpm) — never split them mid-block.
  4. Accumulate sentences until CHUNK_TARGET_TOKENS; flush with
     CHUNK_OVERLAP_SENTENCES carried into the next chunk.
"""

import re
import uuid
from typing import Iterator

from config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_SENTENCES, CHUNK_TARGET_TOKENS

# ── Sentence splitting ────────────────────────────────────────────────────────

_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z가-힣])")


def _split_sentences(text: str) -> list[str]:
    sentences = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = _SENT_END.split(line)
        sentences.extend(p.strip() for p in parts if p.strip())
    return sentences


# ── Section heading detection ─────────────────────────────────────────────────

_HEADING_PATTERNS = [
    re.compile(r"^(chapter|section|part)\b", re.I),
    re.compile(r"^\d+[\.\s]+[A-Z]"),
    re.compile(r"^[IVX]+\.\s+[A-Z]"),
    re.compile(r"^[A-Z][A-Z\s]{4,}$"),
    re.compile(r"^[가-힣]{2,10}\s*([:：]|$)"),
]


def _is_heading(sentence: str) -> bool:
    s = sentence.strip()
    if len(s) > 120:
        return False
    return any(p.match(s) for p in _HEADING_PATTERNS)


# ── Criteria-block detection ──────────────────────────────────────────────────

_CRITERIA_MARKERS = re.compile(
    r"(\d+\s*(ms|mm|mv|bpm|sec|s\b)|criteria|findings?:|"
    r"characterized by|diagnostic|定義|기준|소견)",
    re.I,
)
_LIST_MARKER = re.compile(r"^\s*([•·\-\*]|\d+[.)]\s)")


def _looks_like_criteria(sentence: str) -> bool:
    return bool(_CRITERIA_MARKERS.search(sentence) or _LIST_MARKER.match(sentence))


# ── Token approximation ───────────────────────────────────────────────────────

def _approx_tokens(text: str) -> int:
    return int(len(text.split()) / 0.75)


# ── Core chunker ─────────────────────────────────────────────────────────────

def chunk_pages(pages: list[dict], book_meta: dict) -> Iterator[dict]:
    """
    Takes page dicts from pdf_extractor and yields chunk dicts:
      {id, content, source_book, language, audience_level,
       source_file, page_num, content_type}
    """
    tagged_sentences: list[tuple[str, int]] = []
    for page in pages:
        for sent in _split_sentences(page["text"]):
            tagged_sentences.append((sent, page["page_num"]))

    def flush(bucket: list[tuple[str, int]], in_criteria: bool) -> dict:
        text = " ".join(s for s, _ in bucket)
        start_page = bucket[0][1]
        return {
            "id": str(uuid.uuid4()),
            "content": text,
            "content_type": "criteria" if in_criteria else "narrative",
            "page_num": start_page,
            "source_file": pages[0]["source_file"] if pages else "",
            **book_meta,
        }

    bucket: list[tuple[str, int]] = []
    in_criteria_block = False

    for sent, pnum in tagged_sentences:
        is_head = _is_heading(sent)
        is_crit = _looks_like_criteria(sent)

        if is_head and bucket:
            yield flush(bucket, in_criteria_block)
            bucket = bucket[-CHUNK_OVERLAP_SENTENCES:]
            in_criteria_block = False

        if is_crit and not in_criteria_block and bucket:
            if _approx_tokens(" ".join(s for s, _ in bucket)) > 80:
                yield flush(bucket, False)
                bucket = bucket[-CHUNK_OVERLAP_SENTENCES:]
            in_criteria_block = True

        if not is_crit and in_criteria_block and bucket:
            yield flush(bucket, True)
            bucket = bucket[-CHUNK_OVERLAP_SENTENCES:]
            in_criteria_block = False

        bucket.append((sent, pnum))

        if not in_criteria_block:
            if _approx_tokens(" ".join(s for s, _ in bucket)) >= CHUNK_TARGET_TOKENS:
                yield flush(bucket, False)
                bucket = bucket[-CHUNK_OVERLAP_SENTENCES:]
        elif _approx_tokens(" ".join(s for s, _ in bucket)) > CHUNK_MAX_TOKENS:
            yield flush(bucket, True)
            bucket = bucket[-CHUNK_OVERLAP_SENTENCES:]

    if bucket:
        yield flush(bucket, in_criteria_block)
