import pytest

from app.ingest.chunker import build_chunks
from app.ingest.parsers import load_documents
from app.retrieval import index

CHUNKS = build_chunks(load_documents())
ATTACHMENT_DOCS = {"D05", "D09", "D10"}  # FAQ, release notes 2.1 / 3.0 state attachment limits


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    root = tmp_path_factory.mktemp("idx")
    chroma, bm25 = root / "chroma", root / "bm25.pkl"
    index.build_index(CHUNKS, chroma, bm25)
    return chroma, bm25


def test_metadata_roundtrip_preserves_chunk():
    for c in CHUNKS:
        assert index.from_metadata(c["text"], index.to_metadata(c)) == c


def test_chroma_stores_all_chunks_with_metadata(paths):
    col = index.collection(paths[0])
    assert col.count() == len(CHUNKS)
    got = col.get(ids=[CHUNKS[0]["chunk_id"]], include=["metadatas", "documents"])
    assert index.from_metadata(got["documents"][0], got["metadatas"][0]) == CHUNKS[0]


def test_vector_search_attachment_size(paths):
    hits = index.vector_search("attachment size", k=3, chroma_dir=paths[0])
    assert any("attachment" in c["text"].lower() for c, _ in hits)
    assert {c["doc_id"] for c, _ in hits} & ATTACHMENT_DOCS


def test_bm25_search_attachment_size(paths):
    hits = index.bm25_search("attachment size", k=3, bm25_path=paths[1])
    assert hits and all("attachment" in c["text"].lower() for c, _ in hits[:2])
    assert {c["doc_id"] for c, _ in hits} & ATTACHMENT_DOCS


def test_rebuild_replaces_instead_of_duplicating(paths):
    index.build_index(CHUNKS, paths[0], paths[1])
    assert index.collection(paths[0]).count() == len(CHUNKS)
