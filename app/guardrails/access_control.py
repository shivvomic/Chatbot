"""Restricted-content check.

An unfiltered (admin-level) search is run ONLY to decide whether the question targets content
the role cannot read. Its chunks are never returned, logged or passed to the LLM.
"""
import config
from app.retrieval.search import Hit, can_read, search


def is_restricted(question: str, role: str, allowed_hits: list[Hit]) -> bool:
    """True if the best overall match is unreadable for `role` and the role's own results are weak."""
    if role == "admin":  # admin reads everything: nothing can be hidden from it
        return False
    allowed_top = allowed_hits[0].score if allowed_hits else 0.0
    if allowed_top >= config.RESTRICTED_WEAK_SCORE:
        return False  # the role has good evidence of its own; answer from that
    unfiltered = search(question, "admin", top_n=1)
    if not unfiltered:
        return False
    best = unfiltered[0]
    return best.score >= config.RESTRICTED_MIN_SCORE and not can_read(role, best.chunk)
