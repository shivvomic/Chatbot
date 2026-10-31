"""Shared test fixtures.

* `ensure_index` (session, autouse): builds data/ indexes once if they are missing, so tests
  that search have something to search.
* `fake_llm`: replaces app.llm.generate with a scripted function and records every prompt,
  so pipeline tests run without network or API keys.
* `questions`: questions.jsonl keyed by id.
"""
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

import config
from app import llm
from app.ingest.chunker import build_chunks, write_chunks
from app.ingest.parsers import load_documents
from app.retrieval import index, search

# Matches the <chunk id="..." doc="..."> header written by app/generation/prompts.py
CHUNK_HEADER = re.compile(r'<chunk id="([^"]+)" doc="([^"]+)"')


@pytest.fixture(scope="session", autouse=True)
def ensure_index():
    """Build the real indexes once per test session if they do not exist yet."""
    if not index.is_ready():
        chunks = build_chunks(load_documents())
        write_chunks(chunks)
        index.build_index(chunks)
        search.reset_caches()


@pytest.fixture(scope="session")
def questions() -> dict[str, dict]:
    lines = config.QUESTIONS_PATH.read_text(encoding="utf-8").splitlines()
    return {q["id"]: q for q in (json.loads(line) for line in lines if line)}


@dataclass
class FakeLLM:
    """Scripted stand-in for the provider: `reply(prompt)` decides what the 'model' says."""

    reply: Callable[[str], str] = lambda prompt: '{"status": "not_found", "answer": ""}'
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str, system: str = "", json_mode: bool = False, timeout: float | None = None) -> str:
        self.prompts.append(prompt)
        return self.reply(prompt)

    @staticmethod
    def chunks_in(prompt: str) -> list[tuple[str, str]]:
        """(chunk_id, doc_id) of every chunk shown in a prompt, in order."""
        return CHUNK_HEADER.findall(prompt)


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "generate", fake)
    return fake
