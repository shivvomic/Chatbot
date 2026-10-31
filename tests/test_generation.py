"""Answer generation (JSON + retry), verification and conflict handling - LLM mocked."""
import pytest

from app.generation import answer_generator, answer_verifier, conflict_detector
from app.generation.answer_generator import LLMAnswer, LLMConflict
from app.retrieval.context_builder import ContextChunk
from app.retrieval.search import chunk_store

VALID = '{"status": "answered", "answer": "Five [D02-s2-c1].", "conflicts": [], "clarifying_question": null}'


def _ctx(*ids: str) -> list[ContextChunk]:
    store = chunk_store()
    return [ContextChunk(store[i], store[i]["text"], "hit", 0.9) for i in ids]


# --- generation -------------------------------------------------------------------------

def test_invalid_json_is_retried_once(fake_llm):
    replies = iter(["not json", VALID])
    fake_llm.reply = lambda prompt: next(replies)
    result = answer_generator.generate_answer("q", _ctx("D02-s2-c1"), [])
    assert result.status == "answered" and len(fake_llm.prompts) == 2
    assert "not valid JSON" in fake_llm.prompts[1]


def test_invalid_json_twice_raises(fake_llm):
    fake_llm.reply = lambda prompt: '{"status": "maybe"}'
    with pytest.raises(answer_generator.InvalidAnswerError):
        answer_generator.generate_answer("q", _ctx("D02-s2-c1"), [])


def test_json_fences_are_tolerated():
    assert answer_generator.parse_answer(f"```json\n{VALID}\n```").status == "answered"


# --- verification -----------------------------------------------------------------------

def test_split_sentences_keeps_trailing_citation_on_its_sentence():
    assert answer_verifier.split_sentences("A is 1. [D01-s1-c1] B is 2 [D02-s1-c1].") == [
        "A is 1. [D01-s1-c1]", "B is 2 [D02-s1-c1].",
    ]


def test_unknown_ids_stripped_and_uncited_sentences_removed():
    answer = LLMAnswer(status="answered", answer="Real [D02-s2-c1, X-s9-c9]. Made up [X-s1-c1]. No cite.")
    report = answer_verifier.verify(answer, {"D02-s2-c1"})
    assert report.ok and report.answer == "Real [D02-s2-c1]." and (report.kept, report.total) == (1, 3)


def test_answer_without_valid_citation_fails():
    report = answer_verifier.verify(LLMAnswer(status="answered", answer="Trust me."), {"D02-s2-c1"})
    assert not report.ok


@pytest.mark.parametrize("leak", ["svc-breakglass uses BW-VAULT-0042", "mail priya.nair@brightwave.example",
                                  "call +1-555-0199"])
def test_sensitive_values_fail_verification(leak):
    report = answer_verifier.verify(LLMAnswer(status="answered", answer=f"{leak} [D12-s2-c1]."), {"D12-s2-c1"})
    assert not report.ok


# --- conflicts --------------------------------------------------------------------------

def test_hints_cover_relationship_edges():
    hints = conflict_detector.conflict_hints(_ctx("D01-s2-c1", "D02-s2-c1", "D03-s1-c1"))
    assert any("D01-s2-c1" in h and "D02-s2-c1" in h and "supersedes" in h for h in hints)


def test_resolve_orders_newest_first_and_needs_two_docs():
    ctx = _ctx("D01-s2-c1", "D02-s2-c1")
    raw = [LLMConflict(claim="24 hours", chunk_id="D01-s2-c1"), LLMConflict(claim="1 hour", chunk_id="D02-s2-c1"),
           LLMConflict(claim="ghost", chunk_id="NOPE-s1-c1")]
    conflicts = conflict_detector.resolve_conflicts(raw, ctx)
    assert [c.doc_id for c in conflicts] == ["D02", "D01"] and conflicts[0].version == "3.0"
    assert conflict_detector.resolve_conflicts(raw[:1], ctx) == []


def test_supersession_note_states_edge_or_its_absence():
    versioned = _ctx("D01-s2-c1", "D02-s2-c1")
    raw = [LLMConflict(claim="a", chunk_id="D01-s2-c1"), LLMConflict(claim="b", chunk_id="D02-s2-c1")]
    note = conflict_detector.supersession_note(conflict_detector.resolve_conflicts(raw, versioned), versioned)
    assert "supersedes" in note and "No document states" not in note

    genuine = _ctx("D13-s4-c1", "D11-s1-c1")  # C4: no supersedes edge between these
    raw = [LLMConflict(claim="30 days", chunk_id="D13-s4-c1"), LLMConflict(claim="90 days", chunk_id="D11-s1-c1")]
    note = conflict_detector.supersession_note(conflict_detector.resolve_conflicts(raw, genuine), genuine)
    assert "No document states which of these sources supersedes the other." in note
