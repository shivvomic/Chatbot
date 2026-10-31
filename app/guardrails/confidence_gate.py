"""Confidence gate: decide not_found / needs_clarification before any LLM call.

Thresholds come from config and are tuned with eval/tune_thresholds.py.
"""
import config
from app.guardrails.input_guard import content_words
from app.ingest.relationships import linked
from app.retrieval.search import Hit

GENERIC_CLARIFICATION = (
    "Could you add more detail? For example, which feature, plan, error code or document "
    "are you asking about?"
)


def is_not_found(hits: list[Hit]) -> bool:
    """True when even the best readable chunk is below the relevance threshold."""
    return not hits or hits[0].score < config.NOT_FOUND_THRESHOLD


def _close_unrelated_docs(hits: list[Hit]) -> list[Hit]:
    """One hit per unrelated document among strong hits scoring close to the top hit."""
    if not hits:
        return []
    # Both conditions matter: with weak results every score is ~0 and would look "close".
    floor = max(hits[0].score - config.CLARIFY_SCORE_MARGIN, config.CLARIFY_MIN_SCORE)
    close = [h for h in hits if h.score >= floor]
    picked: list[Hit] = []
    for hit in close:  # keep a hit only if its doc is unrelated to every doc already picked
        doc = hit.chunk["doc_id"]
        if all(doc != p.chunk["doc_id"] and not linked(doc, p.chunk["doc_id"]) for p in picked):
            picked.append(hit)
    return picked


def clarification_needed(question: str, hits: list[Hit]) -> bool:
    """Vague question, or a short question whose close matches span several unrelated topics."""
    words = content_words(question)
    if len(words) <= config.VAGUE_MAX_CONTENT_WORDS:
        return True
    return (
        len(words) <= config.CLARIFY_MAX_CONTENT_WORDS
        and len(_close_unrelated_docs(hits)) >= config.CLARIFY_MIN_TOPICS
    )


def clarifying_question(hits: list[Hit]) -> str:
    """'Did you mean A, B or C?' built from distinct matching sections, or a generic prompt."""
    if is_not_found(hits):
        return GENERIC_CLARIFICATION
    options: list[str] = []
    for hit in hits:
        label = f"{hit.chunk['section']} ({hit.chunk['title']})"
        if hit.chunk["section"] not in {o.split(" (")[0] for o in options}:
            options.append(label)
        if len(options) == config.CLARIFY_OPTIONS:
            break
    if len(options) < 2:
        return GENERIC_CLARIFICATION
    listed = ", ".join(options[:-1]) + f" or {options[-1]}"
    return f"Your question could refer to several topics. Did you mean {listed}?"
