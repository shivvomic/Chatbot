import pytest

from app.ingest.parsers import load_documents

DOCS = load_documents()


def test_all_16_documents_parsed():
    assert len(DOCS) == 16


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.meta["doc_id"])
def test_every_metadata_heading_found_in_order(doc):
    expected = [s["heading"] for s in doc.meta["sections"]]
    assert [s["section"] for s in doc.sections] == expected
    assert all(s["text"] for s in doc.sections)


@pytest.mark.parametrize("doc", [d for d in DOCS if d.meta["format"] == "pdf"], ids=lambda d: d.meta["doc_id"])
def test_pdf_pages_match_metadata(doc):
    assert [s["page"] for s in doc.sections] == [s["page"] for s in doc.meta["sections"]]


def test_html_drops_nav_and_footer():
    text = " ".join(s["text"] for d in DOCS if d.meta["format"] == "html" for s in d.sections)
    assert "All rights reserved" not in text and "Help Center" not in text


def test_markdown_front_matter_removed_and_txt_title_block_skipped():
    for d in DOCS:
        if d.meta["format"] in ("md", "txt"):
            joined = " ".join(s["text"] for s in d.sections)
            assert "author:" not in joined and "Publisher:" not in joined
