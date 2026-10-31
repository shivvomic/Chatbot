"""FastAPI service.

Run: uvicorn app.api.main:app --port 8000

Endpoints (all but /health need an X-API-Key header; the key decides the role):
  GET  /health     liveness, public
  GET  /ready      indexes loaded and models warm
  GET  /documents  documents the caller's role may read
  POST /upload     add a PDF/HTML/MD/TXT file to the index (employee or admin)
  POST /ask        answer a question for the caller's role
  POST /evaluate   run the evaluation harness (admin only)
"""
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from app import pipeline
from app.api.auth import api_keys, current_role, require_role
from app.api.logging_setup import configure_logging
from app.api.middleware import RequestContextMiddleware
from app.api.rate_limit import enforce_rate_limit
from app.guardrails.input_guard import domain_vocabulary
from app.ingest.upload_ingestor import UploadError, ingest_upload
from app.llm import LLMError
from app.retrieval import index, search
from app.schemas import AskResponse

log = logging.getLogger(__name__)
state = {"ready": False}  # flipped by the lifespan once models and indexes are loaded


def warm_up() -> bool:
    """Load models and indexes into memory once; returns whether the index is usable."""
    if not index.is_ready():
        log.warning("index missing: run `python -m app.retrieval.index --rebuild`")
        return False
    index.embedder()
    search.reranker()
    search.chunk_store()
    domain_vocabulary()
    return True


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast on missing configuration, before accepting traffic.
    configure_logging(config.settings.log_level)
    config.require("API_KEYS", f"{config.LLM_PROVIDER.upper()}_API_KEY")
    api_keys()  # parse now so a malformed API_KEYS stops startup
    state["ready"] = warm_up()
    log.info("startup complete", extra={"ready": state["ready"], "llm_provider": config.LLM_PROVIDER})
    yield


app = FastAPI(title="NimbusDesk Documentation Q&A", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type", "X-Request-ID"],
)

# Authenticated + rate-limited routes share these dependencies.
Protected = [Depends(current_role), Depends(enforce_rate_limit)]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=config.QUESTION_MAX_CHARS)


class EvaluateRequest(BaseModel):
    fast: bool = True  # retrieval metrics only; full runs call the LLM for every question
    judge: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready", dependencies=Protected)
def ready() -> dict:
    if not state["ready"]:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Index not loaded")
    return {"ready": True, "chunks": len(search.chunk_store())}


@app.get("/documents", dependencies=[Depends(enforce_rate_limit)])
def documents(role: str = Depends(current_role)) -> list[dict]:
    """One row per document the role can read, with its chunk count."""
    counts: dict[str, int] = defaultdict(int)
    docs: dict[str, dict] = {}
    for chunk in search.chunk_store().values():
        if not search.can_read(role, chunk):
            continue
        counts[chunk["doc_id"]] += 1
        docs.setdefault(chunk["doc_id"], {k: chunk[k] for k in (
            "doc_id", "title", "format", "version", "date", "access_level", "status", "source_file")})
    return [{**d, "chunks": counts[d["doc_id"]]} for d in sorted(docs.values(), key=lambda d: d["doc_id"])]


@app.post("/upload", status_code=status.HTTP_201_CREATED, dependencies=[Depends(enforce_rate_limit)])
async def upload(
    file: UploadFile = File(...),
    access_level: str = Form("public"),
    role: str = Depends(require_role("employee")),
) -> dict:
    """Incrementally index one file. A role can only upload at or below its own access level."""
    if config.ACCESS_RANK.get(access_level, 99) > config.ROLE_RANK[role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"The {role} role cannot upload {access_level} documents")
    content = await file.read(config.UPLOAD_MAX_BYTES + 1)  # read one byte past the limit to detect overflow
    if len(content) > config.UPLOAD_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {config.UPLOAD_MAX_BYTES} bytes")
    try:
        doc = ingest_upload(file.filename or "upload", content, access_level)
    except UploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    state["ready"] = True
    log.info("document uploaded", extra={"doc_id": doc["doc_id"], "chunks": doc["chunks"]})
    return doc


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(enforce_rate_limit)])
def ask(body: AskRequest, role: str = Depends(current_role)) -> AskResponse:
    """Answer for the role bound to the API key (never a role from the body)."""
    if not state["ready"]:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Index not loaded")
    try:
        return pipeline.ask(body.question, role)
    except (LLMError, RuntimeError) as exc:  # provider down / key rejected
        log.error("llm unavailable", extra={"error": str(exc)})  # messages carry status codes, never secrets
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The language model is unavailable") from None


@app.post("/evaluate", dependencies=[Depends(enforce_rate_limit)])
def evaluate(body: EvaluateRequest, _: str = Depends(require_role("admin"))) -> dict:
    """Run the evaluation harness and return its metrics (per-question rows omitted)."""
    from eval.run_eval import run_evaluation  # imported lazily: the eval package is optional at runtime

    results = run_evaluation(fast=body.fast, judge=body.judge)
    return {k: v for k, v in results.items() if k != "rows"}
