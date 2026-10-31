"""Hybrid search: role filter, RRF, reranking, modes and retrieval quality."""
import pytest

from app.retrieval import search as search_mod
from eval.dataset import load_qrels, load_questions
from eval.run_eval import retrieval_metrics


def test_allowed_levels_by_role():
    assert search_mod.allowed_levels("customer") == ["public"]
    assert search_mod.allowed_levels("employee") == ["public", "internal"]
    assert search_mod.allowed_levels("admin") == ["public", "internal", "admin"]
    with pytest.raises(ValueError):
        search_mod.allowed_levels("guest")


def test_rrf_merge_rewards_agreement():
    assert search_mod.rrf_merge([["a", "b", "c"], ["b", "a", "d"]])[:2] == ["a", "b"]
    assert search_mod.rrf_merge([["a"], ["b"]], k=60) == ["a", "b"]
    assert search_mod.rrf_merge([["x", "y"], ["y"]])[0] == "y"


@pytest.mark.parametrize("question,role,allowed", [
    ("What is the temporary password for the break-glass service account?", "customer", {"public"}),
    ("How do I roll back a HelpPilot migration after cutover?", "customer", {"public"}),
    ("How do I roll back a HelpPilot migration after cutover?", "employee", {"public", "internal"}),
    ("Who is the on-call engineering lead?", "admin", {"public", "internal", "admin"}),
])
def test_search_never_returns_unreadable_chunks(question, role, allowed):
    hits = search_mod.search(question, role)
    assert 0 < len(hits) <= 6
    assert {h.chunk["access_level"] for h in hits} <= allowed
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_admin_can_reach_admin_runbook_but_customer_cannot():
    q = "svc-breakglass break-glass service account vault entry"
    assert "D12" in {h.chunk["doc_id"] for h in search_mod.search(q, "admin")}
    assert "D12" not in {h.chunk["doc_id"] for h in search_mod.search(q, "customer")}


def test_direct_and_paraphrase_recall_at_5():
    simple = [q for q in load_questions() if q["category"] in ("direct", "paraphrase")]
    assert retrieval_metrics(simple, load_qrels(), "hybrid_rerank")["recall@5"] >= 0.9


def test_search_modes_return_hits_and_reject_unknown_mode():
    for mode in ("bm25", "vector", "hybrid", "hybrid_rerank"):
        assert search_mod.search("attachment size", "customer", mode=mode)
    with pytest.raises(ValueError):
        search_mod.search("attachment size", "customer", mode="magic")
