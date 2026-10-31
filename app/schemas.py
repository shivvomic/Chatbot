"""Response contracts shared by the pipeline, the API and the evaluation harness."""
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["answered", "conflict", "needs_clarification", "not_found", "refused"]
Role = Literal["customer", "employee", "admin"]


class Citation(BaseModel):
    """One piece of evidence the answer relies on."""

    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: int | None = None
    excerpt: str


class Conflict(BaseModel):
    """One side of a contradiction between documents (listed newest first)."""

    claim: str
    chunk_id: str
    doc_id: str
    version: str | None = None
    date: str | None = None


class AskResponse(BaseModel):
    """The /ask contract."""

    status: Status
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0  # 0..1 evidence strength of the returned answer; 0 when there is none
    conflicts: list[Conflict] = Field(default_factory=list)
    clarifying_question: str | None = None
    latency_ms: int = 0
