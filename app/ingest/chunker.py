"""Clean + redact parsed sections, split long ones, and emit chunks with full metadata.

Pipeline per section: clean whitespace -> redact PII/secrets -> split into ~CHUNK_TOKENS
windows with CHUNK_OVERLAP_TOKENS overlap -> copy document metadata onto every chunk ->
link chunks of one document with prev_id / next_id.

Run: python -m app.ingest.chunker   (writes data/chunks.jsonl)
"""
import json
import re
from pathlib import Path
from typing import TypedDict

import config
from app.ingest.parsers import ParsedDocument, load_all_documents


class Chunk(TypedDict):
    """The fixed chunk contract shared by indexing, retrieval and the API."""

    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: int | None
    text: str
    heading_path: str
    version: str | None
    date: str | None
    access_level: str
    status: str
    supersedes: str | None
    references: list[str]
    prev_id: str | None
    next_id: str | None
    format: str
    source_file: str


# Compiled once; each match becomes "[REDACTED_<NAME>]".
_REDACTORS = [(name, re.compile(p)) for name, p in config.REDACTION_PATTERNS.items()]
_MAX_WORDS = int(config.CHUNK_TOKENS / config.TOKENS_PER_WORD)
_OVERLAP_WORDS = int(config.CHUNK_OVERLAP_TOKENS / config.TOKENS_PER_WORD)


def clean_text(text: str) -> str:
    """Normalise whitespace: no tabs / non-breaking spaces, at most one blank line in a row."""
    text = text.replace("\xa0", " ").replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def redact(text: str) -> str:
    """Replace emails, phone numbers and secret tokens (config.REDACTION_PATTERNS)."""
    for name, pattern in _REDACTORS:
        text = pattern.sub(f"[REDACTED_{name}]", text)
    return text


def split_words(text: str) -> list[str]:
    """Split into windows of at most _MAX_WORDS words, consecutive windows overlapping."""
    words = text.split()
    if len(words) <= _MAX_WORDS:  # short section: keep it whole (keeps its paragraph breaks)
        return [text]
    step = _MAX_WORDS - _OVERLAP_WORDS  # each window starts this many words after the last
    parts = []
    for start in range(0, len(words), step):
        parts.append(" ".join(words[start : start + _MAX_WORDS]))
        if start + _MAX_WORDS >= len(words):  # this window reached the end: no tail window
            break
    return parts


def embedding_text(chunk: Chunk) -> str:
    """The text that gets embedded: heading_path prepended to the chunk body."""
    return f"{chunk['heading_path']}\n{chunk['text']}"


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """All chunks of one document, in reading order, with prev/next links filled."""
    meta = doc.meta
    chunks: list[Chunk] = []
    for index, sec in enumerate(doc.sections, start=1):
        heading = redact(clean_text(sec["section"]))
        # Redact BEFORE splitting so a window boundary can never cut a secret in half.
        for part, body in enumerate(split_words(redact(clean_text(sec["text"]))), start=1):
            # chunk_id = <doc>-s<section index>-c<part>, e.g. D02-s2-c1; every metadata field is copied
            # so retrieval can filter (access_level) and cite (title/section/page) without a lookup.
            chunks.append({
                "chunk_id": f"{meta['doc_id']}-s{index}-c{part}",
                "doc_id": meta["doc_id"],
                "title": meta["title"],
                "section": heading,
                "page": sec["page"],
                "text": body,
                "heading_path": f"{meta['title']}{config.HEADING_SEPARATOR}{heading}",
                "version": meta["version"],
                "date": meta["date"],
                "access_level": meta["access_level"],
                "status": meta["status"],
                "supersedes": meta["supersedes"],
                "references": meta["references"],
                "prev_id": None,
                "next_id": None,
                "format": meta["format"],
                # uploads carry their own path; dataset files live under documents/
                "source_file": meta.get("source_file", f"documents/{meta['file']}"),
            })
    # Link neighbours so context expansion can pull the chunk before / after a hit.
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        prev["next_id"], nxt["prev_id"] = nxt["chunk_id"], prev["chunk_id"]
    return chunks


def build_chunks(docs: list[ParsedDocument]) -> list[Chunk]:
    """Chunks of every document, document by document."""
    return [c for doc in docs for c in chunk_document(doc)]


def write_chunks(chunks: list[Chunk], path: Path = config.CHUNKS_PATH) -> None:
    """Write chunks as JSON lines (one chunk per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")


def read_chunks(path: Path = config.CHUNKS_PATH) -> list[Chunk]:
    """Inverse of write_chunks."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    chunks = build_chunks(load_all_documents())
    write_chunks(chunks)
    print(f"wrote {len(chunks)} chunks to {config.CHUNKS_PATH}")


if __name__ == "__main__":
    main()
