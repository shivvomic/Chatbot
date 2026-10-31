"""Context expansion (step 6): turn reranked hits into the evidence block sent to the LLM.

Order of priority: the reranked hits, then prev/next neighbours of the top hits, then the
best chunk of each document the top hits `reference`. Every added chunk is re-checked
against the role, de-duplicated, sanitised (instruction-like lines removed), tagged when
its document is superseded / stale / unofficial, and the total is capped at
CONTEXT_MAX_TOKENS.
"""
from dataclasses import dataclass, field
from typing import Literal

import config
from app.guardrails.input_guard import sanitize_chunk_text
from app.ingest.chunker import Chunk
from app.retrieval.search import Hit, can_read, chunk_store, rerank

Origin = Literal["hit", "neighbor", "reference"]


@dataclass
class ContextChunk:
    """A chunk as it will be shown to the LLM."""

    chunk: Chunk
    text: str  # sanitised chunk text
    origin: Origin
    score: float | None = None  # reranker score (hits and references only)
    tags: list[str] = field(default_factory=list)

    @property
    def chunk_id(self) -> str:
        return self.chunk["chunk_id"]


def estimate_tokens(text: str) -> int:
    """Same word-based estimate the chunker uses."""
    return int(len(text.split()) * config.TOKENS_PER_WORD)


def _neighbors(hit: Hit, role: str) -> list[Chunk]:
    """The readable chunks just before and after a hit in its document."""
    store = chunk_store()
    ids = (hit.chunk["prev_id"], hit.chunk["next_id"])
    return [store[i] for i in ids if i and i in store and can_read(role, store[i])]


def _reference_best(question: str, hit: Hit, role: str) -> list[Hit]:
    """For each document the hit references, its most relevant readable chunk."""
    best = []
    for doc_id in hit.chunk["references"]:
        candidates = [c for c in chunk_store().values() if c["doc_id"] == doc_id and can_read(role, c)]
        ranked = rerank(question, candidates)
        if ranked:
            best.append(ranked[0])
    return best


def _make(chunk: Chunk, origin: Origin, score: float | None) -> ContextChunk:
    text, changed = sanitize_chunk_text(chunk["text"])
    tags = [chunk["status"]] if chunk["status"] in config.STALE_STATUSES else []
    if changed:
        tags.append("instruction_removed")
    return ContextChunk(chunk, text, origin, score, tags)


def build_context(question: str, hits: list[Hit], role: str) -> list[ContextChunk]:
    """Expanded, de-duplicated, role-safe context, capped at CONTEXT_MAX_TOKENS."""
    # Collect candidates in priority order: hits, then neighbours, then referenced docs.
    candidates: list[ContextChunk] = [_make(h.chunk, "hit", h.score) for h in hits]
    for hit in hits[: config.EXPAND_NEIGHBORS_TOP_N]:
        candidates += [_make(c, "neighbor", None) for c in _neighbors(hit, role)]
    for hit in hits[: config.EXPAND_REFERENCES_TOP_N]:
        candidates += [_make(h.chunk, "reference", h.score) for h in _reference_best(question, hit, role)]

    # Keep each chunk once, re-check access, and stop adding once the token budget is spent.
    context: list[ContextChunk] = []
    seen: set[str] = set()
    budget = config.CONTEXT_MAX_TOKENS
    for item in candidates:
        if item.chunk_id in seen or not can_read(role, item.chunk):  # defence in depth
            continue
        cost = estimate_tokens(item.text)
        if context and cost > budget:  # the top hit is always kept, even if oversized
            continue
        context.append(item)
        seen.add(item.chunk_id)
        budget -= cost
    return context
