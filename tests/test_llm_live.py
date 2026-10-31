"""Real-LLM tests: run only with `pytest -m llm` and an API key for LLM_PROVIDER."""
import pytest

from app import llm
from app.pipeline import ask

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(not llm.is_configured(), reason="no API key for the configured LLM provider"),
]


def test_provider_answers():
    assert llm.generate("Reply with exactly: pong").strip()


def test_direct_question_is_answered_with_citation(questions):
    resp = ask(questions["Q01"]["question"], "customer")
    assert resp.status == "answered" and "5" in resp.answer
    assert any(c.doc_id == "D02" for c in resp.citations)


def test_conflict_question_reports_both_values(questions):
    resp = ask(questions["Q20"]["question"], "customer")
    assert resp.status == "conflict" and {"D05", "D10"} & {c.doc_id for c in resp.conflicts}
