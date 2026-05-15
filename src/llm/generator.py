"""LLM answer generation via vLLM (OpenAI-compatible API)."""

from openai import OpenAI

from config import VLLM_BASE_URL, VLLM_MODEL

_client: OpenAI | None = None

_SYSTEM_PROMPT = """You are a clinical ECG expert. Answer the question using only the provided reference context.
Be concise and clinically accurate. If the context does not contain enough information, say so."""


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-required")
    return _client


def generate(context: str, query: str, model: str = VLLM_MODEL) -> str:
    """Generate an answer from retrieved context using vLLM."""
    response = get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
        temperature=0.2,
        max_tokens=512,
    )
    return response.choices[0].message.content
