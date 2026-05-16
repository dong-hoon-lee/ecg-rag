"""VLM-based image description for ECG textbook images.

Requires a separate vision-capable vLLM server:
  vllm serve Qwen/Qwen2.5-VL-7B-Instruct --port 8081

Set VLM_BACKEND = "vllm" in config.py to enable.
When disabled, image elements get a placeholder description so they
can still be included in layout chunks without blocking the pipeline.
"""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import VLM_BACKEND, VLLM_VLM_BASE_URL, VLLM_VLM_MODEL

VLM_MAX_WORKERS = 6  # concurrent VLM requests

_vlm_client: OpenAI | None = None

_IMAGE_PROMPT = (
    "You are analyzing an image from an ECG (electrocardiography) medical textbook. "
    "Describe the clinical content in detail. "
    "If this is an ECG tracing: describe the rhythm, wave morphology (P, QRS, T), "
    "intervals (PR, QRS, QT), rate, and any notable findings. "
    "If this is an anatomical or physiological diagram: describe the concepts illustrated. "
    "If this shows a flowchart or decision tree: extract the clinical logic and criteria. "
    "Preserve all numerical measurements and diagnostic criteria exactly."
)


def _get_vlm_client() -> OpenAI:
    global _vlm_client
    if _vlm_client is None:
        _vlm_client = OpenAI(base_url=VLLM_VLM_BASE_URL, api_key="not-required")
    return _vlm_client


def _describe_single(image_bytes: bytes, ext: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif", "webp") else "image/png"
    response = _get_vlm_client().chat.completions.create(
        model=VLLM_VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _IMAGE_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        max_tokens=512,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def describe_images_in_pages(pages: list[dict]) -> list[dict]:
    """
    For each image element in pages, add a "description" field.
    VLM calls are executed concurrently (VLM_MAX_WORKERS threads) to
    saturate the vLLM server's internal batching and reduce wall-clock time.

    Modifies pages in-place and returns them.
    """
    if VLM_BACKEND != "vllm":
        for page in pages:
            for elem in page["elements"]:
                if elem["type"] == "image":
                    elem["description"] = (
                        f"[ECG image: {elem['width']}×{elem['height']}px — VLM disabled]"
                    )
        return pages

    # Collect all image elements with their page reference for error reporting
    tasks: list[tuple[dict, int]] = []
    for page in pages:
        for elem in page["elements"]:
            if elem["type"] == "image":
                tasks.append((elem, page["page_num"]))

    def _process(elem_pnum: tuple[dict, int]) -> None:
        elem, pnum = elem_pnum
        try:
            elem["description"] = _describe_single(elem["bytes"], elem.get("ext", "png"))
        except Exception as e:
            print(f"    [warn] VLM failed (p.{pnum}): {e}")
            elem["description"] = f"[ECG image: {elem['width']}×{elem['height']}px]"

    with ThreadPoolExecutor(max_workers=VLM_MAX_WORKERS) as pool:
        list(pool.map(_process, tasks))

    return pages
