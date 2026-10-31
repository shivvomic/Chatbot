"""Hybrid search: access filter -> vector + BM25 -> RRF merge -> cross-encoder rerank.

The role's access filter is applied inside both retrievers, so chunks the role cannot read
are never scored, merged or shown to the LLM.

`mode` exists for the evaluation ablation: bm25 | vector | hybrid (RRF only) |
hybrid_rerank (default, what the pipeline uses).
"""
from functools import cache, lru_cache
from typing import NamedTuple

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

import config
from app.ingest.chunker import Chunk, embedding_text
from app.retrieval import index


class Hit(NamedTuple):
    chunk: Chunk
    score: float  # hybrid_rerank: cross-encoder probability 0..1 (higher = more relevant)


def allowed_levels(role: str) -> list[str]:
    """Access levels a role may read: those whose rank <= the role's rank."""
    if role not in config.ROLE_RANK:
        raise ValueError(f"Unknown role '{role}' (use {', '.join(config.ROLE_RANK)})")
    rank = config.ROLE_RANK[role]
    return [lvl for lvl, r in config.ACCESS_RANK.items() if r <= rank]


def can_read(role: str, chunk: Chunk) -> bool:
    """True if `role` may see `chunk`."""
    return chunk["access_level"] in allowed_levels(role)


@lru_cache(maxsize=1)
def reranker() -> CrossEncoder:
    """The cross-encoder, loaded once per process."""
    return CrossEncoder(config.RERANK_MODEL)


@lru_cache(maxsize=1)
def chunk_store() -> dict[str, Chunk]:
    """Every indexed chunk by chunk_id (used for lookups and context expansion)."""
    return {c["chunk_id"]: c for c in index.load_bm25()["chunks"]}


@cache
def _bm25_for(levels: tuple[str, ...]) -> tuple[BM25Okapi, list[Chunk]]:
    """BM25 built only over chunks the levels may read (cached per access set)."""
    chunks = [c for c in chunk_store().values() if c["access_level"] in levels]
    return BM25Okapi([index.tokenize(embedding_text(c)) for c in chunks]), chunks


def reset_caches() -> None:
    """Forget cached chunk lists / BM25 models (call after the index changes)."""
    chunk_store.cache_clear()
    _bm25_for.cache_clear()


def _vector_ranked(question: str, levels: list[str]) -> list[tuple[str, float]]:
    """(chunk_id, cosine similarity) for the top RETRIEVE_TOP_K readable chunks."""
    res = index.collection().query(
        query_embeddings=index.encode([config.EMBED_QUERY_PREFIX + question]),
        n_results=config.RETRIEVE_TOP_K,
        where={"access_level": {"$in": levels}},  # access filter BEFORE ranking
    )
    return [(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0], strict=True)]


def _bm25_ranked(question: str, levels: list[str]) -> list[tuple[str, float]]:
    """(chunk_id, BM25 score) for the top RETRIEVE_TOP_K readable chunks with score > 0."""
    bm25, chunks = _bm25_for(tuple(levels))
    scores = bm25.get_scores(index.tokenize(question))
    ranked = sorted(zip(chunks, scores, strict=True), key=lambda p: p[1], reverse=True)
    return [(c["chunk_id"], float(s)) for c, s in ranked[: config.RETRIEVE_TOP_K] if s > 0]


def rrf_scores(rankings: list[list[str]], k: int = config.RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(id) = sum over rankings of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def rrf_merge(rankings: list[list[str]], k: int = config.RRF_K) -> list[str]:
    """Chunk ids ordered by fused RRF score, best first."""
    scores = rrf_scores(rankings, k)
    return sorted(scores, key=scores.get, reverse=True)


def rerank(question: str, candidates: list[Chunk]) -> list[Hit]:
    """Score (question, chunk) pairs with the cross-encoder; best first."""
    if not candidates:
        return []
    scores = reranker().predict([(question, embedding_text(c)) for c in candidates])
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: p[1], reverse=True)
    return [Hit(c, float(s)) for c, s in ranked]


def search(
    question: str, role: str, mode: str = "hybrid_rerank", top_n: int = config.RERANK_TOP_N
) -> list[Hit]:
    """Top `top_n` chunks the role may read, best first, with scores."""
    if mode not in config.SEARCH_MODES:
        raise ValueError(f"Unknown search mode '{mode}' (use {', '.join(config.SEARCH_MODES)})")
    # 1. Access filter first: everything below only ever sees chunks of these levels.
    levels = allowed_levels(role)
    store = chunk_store()

    def hits(pairs: list[tuple[str, float]]) -> list[Hit]:
        return [Hit(store[i], s) for i, s in pairs[:top_n] if i in store]

    # 2. Candidate generation: top RETRIEVE_TOP_K from each retriever (skipped when unused).
    vector = _vector_ranked(question, levels) if mode != "bm25" else []
    sparse = _bm25_ranked(question, levels) if mode != "vector" else []
    if mode == "vector":
        return hits(vector)
    if mode == "bm25":
        return hits(sparse)
    # 3. Fuse the two rankings by rank position only (scores are on different scales).
    fused = rrf_scores([[i for i, _ in vector], [i for i, _ in sparse]])
    merged = sorted(fused.items(), key=lambda p: p[1], reverse=True)
    if mode == "hybrid":
        return hits(merged)
    # 4. The cross-encoder reads question + chunk together: slower but much more precise.
    return rerank(question, [store[i] for i, _ in merged if i in store])[:top_n]
