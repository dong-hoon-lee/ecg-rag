"""
ECG RAG FastAPI server.

Run:
  uvicorn api.main:app --reload --port 8000

Endpoints:
  GET  /health       — liveness check
  POST /query        — ECG XML → retrieved context chunks
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.db.qdrant_store import get_client, ensure_collection
from src.ingest.embedder import _get_model
from src.query.retriever import format_context, retrieve
from src.query.xml_parser import parse_xml


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    xml: str = Field(..., description="Raw ECG XML string")
    top_k: int = Field(5, ge=1, le=20)
    language: str | None = Field(None, pattern="^(en|ko)$")
    audience_level: str | None = Field(None, pattern="^(basic|clinical|specialist)$")


class ChunkResult(BaseModel):
    rank: int
    source_book: str
    page_num: int
    score: float
    content: str


class QueryResponse(BaseModel):
    diagnoses: list[str]
    findings: list[str]
    abnormal_params: list[str]
    natural_query: str
    results: list[ChunkResult]
    context: str


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_collection(get_client())
    _get_model()  # pre-load BGE-M3 so first /query isn't slow
    yield


app = FastAPI(
    title="ECG RAG API",
    description="Retrieve ECG knowledge from textbooks given an ECG XML report.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        ctx = parse_xml(req.xml)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    results = retrieve(
        ctx,
        top_k=req.top_k,
        language=req.language,
        audience_level=req.audience_level,
    )

    return QueryResponse(
        diagnoses=ctx.diagnoses,
        findings=ctx.findings,
        abnormal_params=ctx.abnormal_params,
        natural_query=ctx.natural_query,
        results=[
            ChunkResult(
                rank=i,
                source_book=r["source_book"],
                page_num=r["page_num"],
                score=round(r["score"], 4),
                content=r["content"],
            )
            for i, r in enumerate(results, 1)
        ],
        context=format_context(results),
    )
