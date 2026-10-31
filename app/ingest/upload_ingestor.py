"""Ingest an uploaded document into the live indexes (incremental, no full rebuild).

Steps: validate format -> save under data/uploads/ -> parse with the format's parser ->
record it in data/uploads/metadata.json (so --rebuild keeps it) -> chunk (clean + redact) ->
embed only the new chunks into Chroma, re-fit BM25 -> append to chunks.jsonl -> drop caches.
"""
import datetime as dt
import hashlib
import json
import re
import threading
from pathlib import Path

import config
from app.guardrails import input_guard
from app.ingest.chunker import Chunk, chunk_document
from app.ingest.parsers import PARSERS, ParsedDocument
from app.retrieval import index, search

_lock = threading.Lock()  # one upload at a time: doc ids and index writes stay consistent
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadError(ValueError):
    """The upload is not acceptable (bad type, empty, duplicate, no text)."""


def _manifest() -> list[dict]:
    if not config.UPLOADS_METADATA_PATH.exists():
        return []
    return json.loads(config.UPLOADS_METADATA_PATH.read_text(encoding="utf-8"))


def _next_doc_id(manifest: list[dict]) -> str:
    """U001, U002 ... (dataset docs use D01-D16, so ids never collide)."""
    return f"U{len(manifest) + 1:03d}"


def ingest_upload(filename: str, content: bytes, access_level: str) -> dict:
    """Index one uploaded file and return its manifest entry (+ chunk count)."""
    suffix = Path(filename).suffix.lower()
    fmt = config.UPLOAD_EXTENSIONS.get(suffix)
    if fmt is None:
        raise UploadError(f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(config.UPLOAD_EXTENSIONS))}")
    if access_level not in config.ACCESS_RANK:
        raise UploadError(f"access_level must be one of {', '.join(config.ACCESS_RANK)}")
    if not content:
        raise UploadError("The file is empty")

    with _lock:
        manifest = _manifest()
        digest = hashlib.sha256(content).hexdigest()
        if any(m["sha256"] == digest for m in manifest):
            raise UploadError("This file has already been uploaded")

        # Save under a generated, sanitised name: the client's filename is never used as a path.
        doc_id = _next_doc_id(manifest)
        stored_name = f"{doc_id}_{_SAFE_NAME.sub('_', Path(filename).name)[:80]}"
        config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        path = config.UPLOADS_DIR / stored_name
        path.write_bytes(content)

        try:
            sections = PARSERS[fmt](path)
        except Exception as exc:  # corrupt PDF, bad encoding, ...
            path.unlink(missing_ok=True)
            raise UploadError(f"Could not parse the file ({type(exc).__name__})") from None
        if not sections:
            path.unlink(missing_ok=True)
            raise UploadError("No text could be extracted from the file")

        meta = {
            "doc_id": doc_id, "file": stored_name, "format": fmt,
            "title": Path(filename).stem.replace("_", " ").strip() or doc_id,
            "doc_type": "upload", "version": None, "date": dt.date.today().isoformat(),
            "access_level": access_level, "status": "current", "supersedes": None, "references": [],
            "sections": [{"index": i, "heading": s["section"], "page": s["page"]}
                         for i, s in enumerate(sections, start=1)],
            "source_file": f"data/uploads/{stored_name}", "sha256": digest,
        }
        chunks: list[Chunk] = chunk_document(ParsedDocument(meta, sections))
        index.add_chunks(chunks)
        with config.CHUNKS_PATH.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
        config.UPLOADS_METADATA_PATH.write_text(json.dumps(manifest + [meta], indent=2), encoding="utf-8")

        # The in-memory chunk store, per-role BM25 models and domain vocabulary are now stale.
        search.reset_caches()
        input_guard.reset_caches()
    return {**{k: meta[k] for k in ("doc_id", "title", "format", "access_level", "date")}, "chunks": len(chunks)}
