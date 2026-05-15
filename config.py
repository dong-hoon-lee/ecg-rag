from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
QDRANT_PATH = Path(__file__).parent / "qdrant_storage"
COLLECTION_NAME = "ecg_knowledge"

# Knowledge Graph
KG_GRAPH_PATH = Path(__file__).parent / "kg_storage" / "graph.json"
KG_TRIPLES_RAW_PATH = Path(__file__).parent / "kg_storage" / "triples_raw.jsonl"
KG_MODEL_ID = "google/medgemma-4b-it"

# LLM Backend ("vllm" | "none")
LLM_BACKEND = "vllm"
VLLM_BASE_URL = "http://localhost:8080/v1"
VLLM_MODEL = "google/medgemma-4b-it"

EMBEDDING_DIM = 1024  # BGE-M3 dense output

# Chunking targets (in tokens, approximated as words)
CHUNK_TARGET_TOKENS = 500
CHUNK_MAX_TOKENS = 700
CHUNK_OVERLAP_SENTENCES = 2

BOOK_META = {
    "basic-concepts-of-ekg-a-simplified-approach.pdf": {
        "source_book": "basic_concepts_ekg",
        "language": "en",
        "audience_level": "basic",
    },
    "basic-electrocardiography-2nd_ed.pdf": {
        "source_book": "basic_electrocardiography_2ed",
        "language": "en",
        "audience_level": "clinical",
    },
    "만화로보는 심전도.pdf": {
        "source_book": "manga_ecg_ko",
        "language": "ko",
        "audience_level": "basic",
    },
    "electrocardiography-of-inherited-arrhythmias-and-cardiomyopathies-from-basic-science-to-clinical-practice-1st-ed.pdf": {
        "source_book": "inherited_arrhythmias",
        "language": "en",
        "audience_level": "specialist",
    },
    "marriotts-practical-electrocardiography-13th-edition 번역.pdf": {
        "source_book": "marriotts_13ed_ko",
        "language": "ko",
        "audience_level": "clinical",
    },
    "marriotts-practical-electrocardiography-13th-edition.pdf": {
        "source_book": "marriotts_13ed_en",
        "language": "en",
        "audience_level": "clinical",
    },
    "goldbergers-clinical-electrocardiography-a-simplified-approach-10th_ed.pdf": {
        "source_book": "goldbergers_10ed",
        "language": "en",
        "audience_level": "clinical",
    },
}
