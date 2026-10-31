"""Evaluation harness: retrieval metrics, pipeline metrics (fake LLM) and report rendering."""
import json

from app.schemas import AskResponse, Citation
from eval import run_eval
from eval.dataset import load_qrels, load_questions
from eval.report import render_report


def test_qrels_load_section_level_relevance():
    qrels = load_qrels()
    assert ("D02", "2. Signing In and Passwords") in qrels["Q01"]


def test_retrieval_metrics_are_bounded():
    subset = [q for q in load_questions() if q["id"] in ("Q01", "Q04", "Q20")]
    metrics = run_eval.retrieval_metrics(subset, load_qrels(), "hybrid_rerank")
    assert metrics["n"] == 3 and 0 <= metrics["recall@1"] <= metrics["recall@5"] <= 1 and metrics["mrr"] > 0


def test_leak_and_citation_scoring():
    q = {"gold_evidence": [{"doc_id": "D02", "section": "S"}], "expected_status": "answered",
         "must_not_include": ["secret"]}
    resp = AskResponse(status="answered", answer="The SECRET is x", citations=[
        Citation(chunk_id="D02-s1-c1", doc_id="D02", title="t", section="S", excerpt="e"),
        Citation(chunk_id="D03-s1-c1", doc_id="D03", title="t", section="Z", excerpt="e")])
    assert run_eval.leaked(resp, q["must_not_include"]) == ["secret"]
    assert run_eval.citation_scores(resp, q) == (0.5, 1.0)


def test_pipeline_metrics_and_report(fake_llm):
    def reply(prompt: str) -> str:
        chunk_id, _ = fake_llm.chunks_in(prompt)[0]
        return json.dumps({"status": "answered", "answer": f"See [{chunk_id}].", "conflicts": []})
    fake_llm.reply = reply
    subset = [q for q in load_questions() if q["id"] in ("Q01", "Q32", "Q43")]
    metrics, rows = run_eval.pipeline_metrics(subset, judge=False)
    assert metrics["n"] == 3 and metrics["status_accuracy"] == 1.0 and metrics["leakage_rate"] == 0.0
    assert metrics["confusion_matrix"]["refused"]["refused"] == 1

    results = {"mode": "full", "judge": False, "pipeline": metrics, "failures": run_eval.failure_cases(rows),
               "retrieval": {"bm25": {"recall@1": 0.5, "mrr": 0.6, "n": 3}}}
    report = render_report(results)
    assert "## Pipeline" in report and "Confusion matrix" in report and "| bm25 | 0.5 | 0.6 |" in report
