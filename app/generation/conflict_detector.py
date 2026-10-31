"""Conflict detection (step 10).

1. `conflict_hints` (before the LLM): pairs of context chunks from different documents that
   may disagree - a conflicts_with / supersedes edge in relationships.json, or two strong hits
   with a different version or date. The LLM is asked to compare their claims.
2. `resolve_conflicts` (after the LLM): keep only claims whose chunk is in context, fill doc,
   version and date from metadata, order newest first. Two or more documents -> conflict.
3. `supersession_note`: a metadata-derived sentence saying which source is newest and whether
   any document states that it supersedes another (or explicitly that none does).
"""
from itertools import combinations

import config
from app.generation.answer_generator import LLMConflict
from app.ingest.relationships import edges_between, supersedes
from app.retrieval.context_builder import ContextChunk
from app.schemas import Conflict


def _label(item: ContextChunk) -> str:
    c = item.chunk
    return f"{c['chunk_id']} ({c['title']}, version {c['version'] or 'n/a'}, {c['date'] or 'undated'})"


def conflict_hints(context: list[ContextChunk]) -> list[str]:
    """Human-readable candidate pairs for the LLM to compare."""
    hints = []
    for a, b in combinations(context, 2):
        doc_a, doc_b = a.chunk["doc_id"], b.chunk["doc_id"]
        if doc_a == doc_b:
            continue
        # Signal 1: metadata says the docs conflict or one supersedes the other.
        edge_types = {e["type"] for e in edges_between(doc_a, doc_b)} - {"references"}
        # Signal 2: both are strong hits on the question but come from different versions/dates.
        strong = all(
            x.origin == "hit" and (x.score or 0) >= config.CONFLICT_MIN_SCORE for x in (a, b)
        )
        differs = (a.chunk["version"], a.chunk["date"]) != (b.chunk["version"], b.chunk["date"])
        if edge_types or (strong and differs):
            reason = ", ".join(sorted(edge_types)) or "different version/date"
            hints.append(f"{_label(a)} vs {_label(b)} [{reason}]")
    return hints


def resolve_conflicts(raw: list[LLMConflict], context: list[ContextChunk]) -> list[Conflict]:
    """Validated conflicts, newest first; empty unless at least two documents disagree."""
    by_id = {i.chunk_id: i.chunk for i in context}
    conflicts: list[Conflict] = []
    seen: set[str] = set()
    for item in raw:
        chunk = by_id.get(item.chunk_id)
        if chunk is None or item.chunk_id in seen or not item.claim.strip():
            continue  # claim cites a chunk the model never saw: drop it
        seen.add(item.chunk_id)
        conflicts.append(Conflict(
            claim=item.claim.strip(), chunk_id=item.chunk_id, doc_id=chunk["doc_id"],
            version=chunk["version"], date=chunk["date"],
        ))
    if len({c.doc_id for c in conflicts}) < 2:
        return []
    return sorted(conflicts, key=lambda c: c.date or "", reverse=True)


def supersession_note(conflicts: list[Conflict], context: list[ContextChunk]) -> str:
    """'Newest source: ...' plus which document supersedes which, or that none says so."""
    titles = {i.chunk["doc_id"]: i.chunk["title"] for i in context}
    statuses = {i.chunk["doc_id"]: i.chunk["status"] for i in context}
    newest = conflicts[0]
    parts = [
        f"Newest source: {titles[newest.doc_id]} (version {newest.version or 'n/a'}, "
        f"{newest.date or 'undated'})."
    ]
    docs = list(dict.fromkeys(c.doc_id for c in conflicts))
    stated = [
        f"{titles[a]} supersedes {titles[b]}."
        for a, b in ((x, y) for x in docs for y in docs if x != y)
        if supersedes(a, b)
    ]
    parts += stated or ["No document states which of these sources supersedes the other."]
    parts += [f"{titles[d]} is marked {statuses[d]}." for d in docs if statuses[d] in config.STALE_STATUSES]
    return " ".join(parts)
