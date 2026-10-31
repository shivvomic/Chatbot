"""The whole question-answering flow: ask(question, role) -> AskResponse.

  1. input guard      injection / out-of-scope / credential request  -> refused
  2. search           role-filtered hybrid retrieval + rerank
  3. access control   best overall match is unreadable for the role   -> refused
  4. confidence gate  vague question                                 -> needs_clarification
                      top score below threshold (no LLM call)        -> not_found
  5. context          neighbours + references, sanitised, token-capped
  6. generation       grounded JSON answer with [chunk_id] citations
  7. verification     citations / leaks; one regeneration, then      -> not_found
  8. conflicts        >= 2 documents disagree                        -> conflict
"""
import logging
import time

from app.generation.answer_generator import InvalidAnswerError, LLMAnswer, generate_answer
from app.generation.answer_verifier import Verification, verify
from app.generation.conflict_detector import conflict_hints, resolve_conflicts, supersession_note
from app.guardrails import confidence_gate, input_guard
from app.guardrails.access_control import is_restricted
from app.retrieval.context_builder import ContextChunk, build_context
from app.retrieval.search import Hit, search
from app.schemas import AskResponse, Citation
from config import EXCERPT_CHARS, VERIFY_REGENERATIONS

log = logging.getLogger(__name__)

# User-facing messages. Refusals never mention what restricted content exists.
REFUSED_INJECTION = (
    "I can't follow instructions that try to change how I work. "
    "Please ask a question about the documentation."
)
REFUSED_SCOPE = "I can only answer questions about the NimbusDesk documentation."
REFUSED_SECRET = "I can't share passwords, secrets, tokens or credentials."
REFUSED_RESTRICTED = (
    "I can't answer that with your access level. "
    "Please contact an administrator if you need this information."
)
NOT_FOUND = "I could not find this in the documentation available to you."
NEEDS_DETAIL = "I need a little more detail to answer this."


def _refuse(message: str, reason: str) -> AskResponse:
    # Only the reason code is logged: never the question or any chunk text for refusals.
    log.info("refused", extra={"status": "refused", "reason": reason})
    return AskResponse(status="refused", answer=message)


def _citations(ids: list[str], context: list[ContextChunk]) -> list[Citation]:
    by_id = {i.chunk_id: i for i in context}
    return [
        Citation(
            chunk_id=i, doc_id=by_id[i].chunk["doc_id"], title=by_id[i].chunk["title"],
            section=by_id[i].chunk["section"], page=by_id[i].chunk["page"],
            excerpt=by_id[i].text[:EXCERPT_CHARS],
        )
        for i in ids
    ]


def _confidence(report: Verification, context: list[ContextChunk], hits: list[Hit]) -> float:
    """Best reranker score among cited chunks, scaled by the share of sentences that survived."""
    scores = {i.chunk_id: i.score for i in context if i.score is not None}
    cited = [scores[i] for i in report.cited_ids if i in scores] or [hits[0].score]
    return round(max(cited) * (report.kept / max(report.total, 1)), 3)


def _generate_verified(
    question: str, context: list[ContextChunk]
) -> tuple[LLMAnswer, Verification] | None:
    """Generate + verify, regenerating with feedback on failure; None if it never passes."""
    hints = conflict_hints(context)
    context_ids = {i.chunk_id for i in context}
    feedback = None
    for _ in range(1 + VERIFY_REGENERATIONS):
        try:
            result = generate_answer(question, context, hints, feedback)
        except InvalidAnswerError:
            log.warning("invalid LLM JSON after retry")
            return None
        report = verify(result, context_ids)
        if report.ok:
            return result, report
        feedback = " ".join(report.problems) + "."
        log.warning("verification failed", extra={"problems": report.problems})
    return None


def _decide(question: str, role: str) -> AskResponse:
    if not question:
        return AskResponse(status="needs_clarification", answer=NEEDS_DETAIL,
                           clarifying_question="What would you like to know about NimbusDesk?")

    # 1. input guard
    guard = input_guard.classify(question)
    if guard.label == "injection":
        return _refuse(REFUSED_INJECTION, guard.reason)
    if guard.label == "out_of_scope":
        return _refuse(REFUSED_SCOPE, guard.reason)
    if input_guard.is_secret_request(question):
        return _refuse(REFUSED_SECRET, "secret_request")

    # 2-3. retrieval (role-filtered) and restricted-content check
    hits = search(question, role)
    if is_restricted(question, role, hits):
        return _refuse(REFUSED_RESTRICTED, "restricted_content")

    # 4. confidence gate (no LLM call)
    if confidence_gate.clarification_needed(question, hits):
        return AskResponse(status="needs_clarification", answer=NEEDS_DETAIL,
                           clarifying_question=confidence_gate.clarifying_question(hits))
    if confidence_gate.is_not_found(hits):
        return AskResponse(status="not_found", answer=NOT_FOUND)

    # 5-7. context, grounded generation, verification
    context = build_context(question, hits, role)
    outcome = _generate_verified(question, context)
    if outcome is None:
        return AskResponse(status="not_found", answer=NOT_FOUND)
    result, report = outcome
    if result.status == "not_found":
        return AskResponse(status="not_found", answer=NOT_FOUND)
    if result.status == "needs_clarification":
        return AskResponse(status="needs_clarification", answer=NEEDS_DETAIL,
                           clarifying_question=result.clarifying_question
                           or confidence_gate.clarifying_question(hits))

    # 8. conflicts: trust validated claims from >= 2 documents, whatever status the LLM chose
    conflicts = resolve_conflicts(result.conflicts, context)
    answer = report.answer
    if conflicts:
        answer = f"{answer} {supersession_note(conflicts, context)}".strip()
    return AskResponse(
        status="conflict" if conflicts else "answered",
        answer=answer,
        citations=_citations(report.cited_ids, context),
        confidence=_confidence(report, context, hits),
        conflicts=conflicts,
    )


def ask(question: str, role: str) -> AskResponse:
    """Answer `question` for `role` using only documents that role may read."""
    start = time.perf_counter()
    response = _decide(question.strip(), role)
    response.latency_ms = int((time.perf_counter() - start) * 1000)
    log.info("ask_completed", extra={"status": response.status, "role": role, "latency_ms": response.latency_ms,
                                "citations": [c.chunk_id for c in response.citations]})
    return response
