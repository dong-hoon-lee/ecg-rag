"""MedGemma-based triple extraction from ECG text chunks."""

import json
import logging
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from config import KG_MODEL_ID

logger = logging.getLogger(__name__)

ENTITY_TYPES = [
    "Diagnosis", "ECGFinding", "Parameter", "Measurement",
    "Treatment", "Drug", "Concept",
]
RELATION_TYPES = [
    "has_criteria", "associated_with", "differentiates_from",
    "caused_by", "treated_with", "measured_by",
    "indicates", "excludes", "normal_range", "abnormal_when",
]

_SYSTEM = (
    "You are a medical knowledge graph extractor specializing in electrocardiography (ECG). "
    "Extract entity-relation-entity triples from medical text. "
    "Output ONLY a valid JSON array. No explanation, no markdown fences."
)

_USER_TMPL = """\
Extract ECG knowledge graph triples from the text below.

Entity types: {entity_types}
Relation types: {relation_types}

Rules:
- Normalize entity names to title case (e.g. "atrial fibrillation" → "Atrial Fibrillation")
- Only extract clinically meaningful ECG relationships
- If no relevant triples exist, return []

Text:
{text}

JSON array:"""


def load_model(model_id: str = KG_MODEL_ID) -> tuple[Any, Any]:
    """Load MedGemma model and tokenizer onto GPU."""
    logger.info("Loading %s ...", model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    logger.info("Model loaded.")
    return model, tokenizer


def _build_prompt(text: str, tokenizer: Any) -> str:
    messages = [
        {
            "role": "user",
            "content": f"{_SYSTEM}\n\n{_USER_TMPL.format(text=text, entity_types=', '.join(ENTITY_TYPES), relation_types=', '.join(RELATION_TYPES))}",
        },
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def _parse_json(raw: str) -> list[dict]:
    """Extract JSON array from model output, tolerating surrounding text."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        triples = json.loads(m.group())
        if not isinstance(triples, list):
            return []
        return [
            t for t in triples
            if all(k in t for k in ("head", "head_type", "relation", "tail", "tail_type"))
        ]
    except json.JSONDecodeError:
        return []


@torch.inference_mode()
def extract_triples(
    model: Any,
    tokenizer: Any,
    text: str,
    source_meta: dict,
    max_new_tokens: int = 512,
) -> list[dict]:
    """
    Run MedGemma on one chunk and return triples with source provenance.
    Each triple: {head, head_type, relation, tail, tail_type, source_book, page_num}
    """
    prompt = _build_prompt(text, tokenizer)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    out = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        temperature=1.0,
        pad_token_id=tokenizer.eos_token_id,
    )
    generated = tokenizer.decode(
        out[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )
    triples = _parse_json(generated)
    for t in triples:
        t["source_book"] = source_meta.get("source_book", "")
        t["page_num"] = source_meta.get("page_num")
    return triples
