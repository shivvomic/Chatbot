"""Context expansion: neighbours, references, role safety, tags, de-duplication and the token cap."""
import config
from app.retrieval import context_builder
from app.retrieval.search import Hit, chunk_store, search


def test_neighbors_tags_and_no_duplicates():
    hits = search("How many failed sign-ins lock an account in NimbusDesk 3.0?", "customer")
    context = context_builder.build_context("lockout", hits, "customer")
    ids = [c.chunk_id for c in context]
    assert len(ids) == len(set(ids))
    assert any(c.origin == "neighbor" for c in context)
    d01 = [c for c in context if c.chunk["doc_id"] == "D01"]
    assert d01 and all("superseded" in c.tags for c in d01)


def test_references_are_followed_for_readable_docs():
    store = chunk_store()
    sso = store["D08-s1-c1"]  # SSO setup guide references the v3 user manual (D02)
    context = context_builder.build_context("Which plan has SSO?", [Hit(sso, 0.9)], "customer")
    assert any(c.origin == "reference" and c.chunk["doc_id"] == "D02" for c in context)


def test_references_to_unreadable_docs_are_skipped():
    store = chunk_store()
    public = dict(store["D06-s1-c1"], references=["D12"])  # pretend a public doc links to the admin runbook
    context = context_builder.build_context("recovery", [Hit(public, 0.9)], "customer")
    assert all(c.chunk["access_level"] == "public" for c in context)


def test_instruction_lines_are_removed_and_tagged():
    poisoned = chunk_store()["D15-s4-c1"]
    context = context_builder.build_context("tips", [Hit(poisoned, 0.5)], "customer")
    item = context[0]
    assert "instruction_removed" in item.tags and "ignore all previous" not in item.text.lower()


def test_token_cap_keeps_only_what_fits(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_MAX_TOKENS", 1)
    hits = search("What is the maximum attachment size?", "customer")
    context = context_builder.build_context("attachment size", hits, "customer")
    assert [c.chunk_id for c in context] == [hits[0].chunk["chunk_id"]]  # top hit always kept
