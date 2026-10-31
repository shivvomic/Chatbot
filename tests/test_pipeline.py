"""End-to-end pipeline: one or more tests per status, using questions.jsonl and a fake LLM.

The fake LLM reads the chunk ids out of the prompt and answers like a well-behaved model
would, so these tests check the pipeline's gating, verification and assembly logic.
"""
import json

from app.pipeline import NOT_FOUND, ask


def _answer(status: str, answer: str = "", conflicts=None, clarifying_question=None) -> str:
    return json.dumps({"status": status, "answer": answer, "conflicts": conflicts or [],
                       "clarifying_question": clarifying_question})


def cite_first(fake_llm):
    """Fake model: one sentence citing the first chunk it was shown."""
    def reply(prompt: str) -> str:
        chunk_id, _ = fake_llm.chunks_in(prompt)[0]
        return _answer("answered", f"The answer is in the documentation [{chunk_id}].")
    return reply


# --- answered ---------------------------------------------------------------------------

def test_answered_with_citations_and_confidence(fake_llm, questions):
    fake_llm.reply = cite_first(fake_llm)
    resp = ask(questions["Q01"]["question"], "customer")
    assert resp.status == "answered"
    assert resp.citations and resp.citations[0].doc_id == "D02" and resp.citations[0].excerpt
    assert 0 < resp.confidence <= 1 and resp.latency_ms >= 0


def test_customer_prompt_never_contains_unreadable_chunks(fake_llm, questions):
    fake_llm.reply = cite_first(fake_llm)
    for qid in ("Q01", "Q13", "Q16", "Q44"):
        ask(questions[qid]["question"], "customer")
    shown = {doc for prompt in fake_llm.prompts for _, doc in fake_llm.chunks_in(prompt)}
    assert shown and not shown & {"D11", "D12", "D14", "D16"}


def test_poisoned_chunk_reaches_llm_only_sanitised(fake_llm, questions):
    fake_llm.reply = cite_first(fake_llm)
    ask(questions["Q44"]["question"], "customer")
    assert all("ignore all previous instructions" not in p.lower() for p in fake_llm.prompts)


# --- conflict ---------------------------------------------------------------------------

def test_conflict_lists_both_sides_newest_first(fake_llm, questions):
    def reply(prompt: str) -> str:
        by_doc = {doc: cid for cid, doc in reversed(fake_llm.chunks_in(prompt))}
        old, new = by_doc["D05"], by_doc["D10"]
        return _answer("conflict", f"The FAQ says 25 MB [{old}]. The 3.0 notes say 50 MB [{new}].",
                       [{"claim": "25 MB", "chunk_id": old}, {"claim": "50 MB", "chunk_id": new}])
    fake_llm.reply = reply
    resp = ask(questions["Q20"]["question"], "customer")
    assert resp.status == "conflict"
    assert [c.doc_id for c in resp.conflicts] == ["D10", "D05"]  # newest first
    assert resp.conflicts[0].date == "2025-06-10" and "Newest source" in resp.answer


def test_single_document_conflict_is_downgraded_to_answered(fake_llm, questions):
    def reply(prompt: str) -> str:
        cid, _ = fake_llm.chunks_in(prompt)[0]
        return _answer("conflict", f"Value [{cid}].", [{"claim": "x", "chunk_id": cid}])
    fake_llm.reply = reply
    assert ask(questions["Q04"]["question"], "customer").status == "answered"


# --- needs_clarification ----------------------------------------------------------------

def test_vague_question_is_clarified_without_llm(fake_llm, questions):
    resp = ask(questions["Q25"]["question"], "customer")
    assert resp.status == "needs_clarification" and resp.clarifying_question
    assert fake_llm.prompts == []


def test_weak_unrelated_hits_do_not_trigger_clarification(questions):
    # Regression: Q44/Q35 have tiny scores everywhere; noise hits must not count as "close topics".
    from app.guardrails.confidence_gate import clarification_needed
    from app.retrieval.search import search
    for qid in ("Q35", "Q44"):
        q = questions[qid]["question"]
        assert not clarification_needed(q, search(q, "customer")), qid


def test_llm_can_ask_for_clarification(fake_llm, questions):
    fake_llm.reply = lambda prompt: _answer("needs_clarification", clarifying_question="Which plan are you on?")
    resp = ask(questions["Q28"]["question"], "customer")
    assert resp.status == "needs_clarification" and resp.clarifying_question == "Which plan are you on?"


# --- not_found --------------------------------------------------------------------------

def test_low_score_is_not_found_without_llm(fake_llm, questions):
    resp = ask(questions["Q32"]["question"], "customer")
    assert resp.status == "not_found" and resp.answer == NOT_FOUND and fake_llm.prompts == []


def test_llm_not_found_is_respected(fake_llm, questions):
    fake_llm.reply = lambda prompt: _answer("not_found")
    resp = ask(questions["Q31"]["question"], "customer")
    assert resp.status == "not_found" and resp.citations == []


def test_uncited_answer_is_regenerated_once_then_not_found(fake_llm, questions):
    fake_llm.reply = lambda prompt: _answer("answered", "Probably five.")
    resp = ask(questions["Q01"]["question"], "customer")
    assert resp.status == "not_found" and len(fake_llm.prompts) == 2
    assert "rejected" in fake_llm.prompts[1]


def test_leaking_answer_is_regenerated(fake_llm, questions):
    replies = iter(["leak", "clean"])

    def reply(prompt: str) -> str:
        cid, _ = fake_llm.chunks_in(prompt)[0]
        text = "Mail priya.nair@brightwave.example" if next(replies) == "leak" else "Five passwords"
        return _answer("answered", f"{text} [{cid}].")
    fake_llm.reply = reply
    resp = ask(questions["Q01"]["question"], "customer")
    assert resp.status == "answered" and "@" not in resp.answer


# --- refused ----------------------------------------------------------------------------

def test_restricted_questions_are_refused_without_leaking(fake_llm, questions):
    for qid in ("Q38", "Q39", "Q40", "Q41", "Q42"):
        q = questions[qid]
        resp = ask(q["question"], q["user_role"])
        assert resp.status == "refused", qid
        blob = resp.model_dump_json().lower()
        assert not [s for s in q["must_not_include"] if s.lower() in blob], qid
    assert fake_llm.prompts == []  # restricted text never reached the LLM


def test_employee_can_read_internal_doc(fake_llm, questions):
    fake_llm.reply = cite_first(fake_llm)
    resp = ask(questions["Q41"]["question"], "employee")
    assert resp.status == "answered" and resp.citations[0].doc_id == "D14"


def test_injection_secret_and_out_of_scope_are_refused(fake_llm, questions):
    for qid in ("Q37", "Q43", "Q45", "Q47", "Q48"):
        assert ask(questions[qid]["question"], "customer").status == "refused", qid
    assert fake_llm.prompts == []
