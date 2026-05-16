"""Table-to-text conversion for ECG textbook tables.

Two modes (controlled by TABLE_LLM_SUMMARY in config.py):
  True  — summarize table content with LLM (medgemma via vLLM)
  False — store raw markdown as-is (faster, lossless)
"""

import uuid

from openai import OpenAI

from config import LLM_BACKEND, TABLE_LLM_SUMMARY, VLLM_BASE_URL, VLLM_MODEL

_llm_client: OpenAI | None = None

_TABLE_PROMPT = (
    "The following is a table extracted from an ECG (electrocardiography) medical textbook. "
    "Write a concise clinical summary of the information in this table as a paragraph. "
    "Preserve all numerical values, units, diagnostic thresholds, and clinical criteria exactly. "
    "Do not add interpretation beyond what the table states.\n\n"
    "Table:\n{markdown}"
)


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-required")
    return _llm_client


def _summarize(markdown: str) -> str:
    response = _get_llm_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=[
            {"role": "user", "content": _TABLE_PROMPT.format(markdown=markdown)},
        ],
        max_tokens=300,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def make_table_chunks(pages: list[dict], book_meta: dict) -> list[dict]:
    """
    For each table in pages, produce a chunk dict with either an LLM summary
    or the raw markdown (based on TABLE_LLM_SUMMARY config).

    Always returns chunks regardless of LLM_BACKEND — markdown fallback is used
    when LLM summary is disabled or fails.
    """
    chunks = []
    for page in pages:
        for tbl in page.get("tables", []):
            markdown = tbl["markdown"]
            if not markdown.strip():
                continue

            if TABLE_LLM_SUMMARY and LLM_BACKEND == "vllm":
                try:
                    content = _summarize(markdown)
                except Exception as e:
                    print(f"    [warn] Table LLM summary failed (p.{page['page_num']}): {e}")
                    content = markdown
            else:
                content = markdown

            chunks.append({
                "id": str(uuid.uuid4()),
                "content": content,
                "content_type": "table",
                "page_num": page["page_num"],
                "source_file": page["source_file"],
                **book_meta,
            })

    return chunks
