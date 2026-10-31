import json

import config
from app.ingest import chunker
from app.ingest.chunker import Chunk, build_chunks, clean_text, embedding_text, redact, split_words
from app.ingest.parsers import load_documents

DOCS = load_documents()
CHUNKS = build_chunks(DOCS)
REGISTER = json.loads(config.SENSITIVE_REGISTER_PATH.read_text())["items"]
PII_KINDS = {"email", "phone", "secret_token", "vault_reference"}


def test_redact_patterns_and_no_false_positive_on_dates():
    out = redact("mail a.b@x.example or +1-555-0142, key NB-STG-7F3A9C21D84E5B60, BW-VAULT-0042, 2025-10-01")
    assert "@" not in out and "555" not in out and "NB-STG" not in out and "VAULT" not in out
    assert "2025-10-01" in out


def test_clean_text_collapses_whitespace():
    assert clean_text("a \t b\xa0c  \n\n\n\n d ") == "a b c\n\nd"


def test_planted_pii_does_not_survive_in_any_chunk():
    values = [i["value"] for i in REGISTER if i["kind"] in PII_KINDS]
    assert len(values) == 8
    for c in CHUNKS:
        blob = json.dumps(c)
        assert not [v for v in values if v in blob], c["chunk_id"]


def test_public_chunks_have_no_register_item_except_injection_text():
    public = [c for c in CHUNKS if c["access_level"] == "public"]
    assert public
    for c in public:
        for item in REGISTER:
            if item["kind"] != "prompt_injection":
                assert item["value"] not in json.dumps(c)


def test_every_chunk_has_full_metadata():
    keys = set(Chunk.__annotations__)
    metas = {m.meta["doc_id"]: m.meta for m in DOCS}
    ids = [c["chunk_id"] for c in CHUNKS]
    assert len(ids) == len(set(ids))
    for c in CHUNKS:
        assert set(c) == keys
        m = metas[c["doc_id"]]
        assert c["text"] and c["section"] and c["heading_path"] == f"{m['title']} > {c['section']}"
        assert (c["title"], c["version"], c["date"], c["access_level"], c["status"], c["format"]) == (
            m["title"], m["version"], m["date"], m["access_level"], m["status"], m["format"])
        assert c["supersedes"] == m["supersedes"] and c["references"] == m["references"]
        assert (c["page"] is not None) == (m["format"] == "pdf")


def test_prev_next_links_form_a_chain_per_document():
    by_id = {c["chunk_id"]: c for c in CHUNKS}
    for doc_id in {c["doc_id"] for c in CHUNKS}:
        doc = [c for c in CHUNKS if c["doc_id"] == doc_id]
        assert doc[0]["prev_id"] is None and doc[-1]["next_id"] is None
        for a, b in zip(doc, doc[1:], strict=False):
            assert a["next_id"] == b["chunk_id"] and b["prev_id"] == a["chunk_id"]
    assert all(by_id[c["next_id"]]["prev_id"] == c["chunk_id"] for c in CHUNKS if c["next_id"])


def test_long_section_is_split_with_overlap():
    words = [f"w{i}" for i in range(1000)]
    parts = split_words(" ".join(words))
    assert len(parts) > 1
    assert all(len(p.split()) <= chunker._MAX_WORDS for p in parts)
    assert parts[0].split()[-chunker._OVERLAP_WORDS:] == parts[1].split()[: chunker._OVERLAP_WORDS]
    assert parts[-1].split()[-1] == "w999"


def test_embedding_text_prepends_heading_path():
    c = CHUNKS[0]
    assert embedding_text(c).startswith(c["heading_path"] + "\n")


def test_write_and_read_roundtrip(tmp_path):
    path = tmp_path / "chunks.jsonl"
    chunker.write_chunks(CHUNKS, path)
    assert chunker.read_chunks(path) == CHUNKS
