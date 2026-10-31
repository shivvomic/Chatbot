"""Build and query the two indexes: ChromaDB (dense) and BM25 (sparse).

Run: python -m app.retrieval.index --rebuild
     python -m app.retrieval.index --search "attachment size"   (raw vector + BM25 hits)

The searches here are raw: no access filtering or reranking (see search.py for that).
The BM25 pickle also stores the full chunk list, which doubles as the chunk store.
"""
import argparse
import pickle
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import config
from app.ingest.chunker import Chunk, build_chunks, embedding_text, write_chunks
from app.ingest.parsers import load_all_documents

_TOKEN = re.compile(r"\w+")
_LIST_FIELDS = ("references",)  # Chroma metadata cannot hold lists: stored comma-joined
_OPTIONAL_FIELDS = ("page", "supersedes", "prev_id", "next_id", "version", "date")


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens; shared by BM25 indexing and querying."""
    return _TOKEN.findall(text.lower())


@lru_cache(maxsize=1)
def embedder() -> SentenceTransformer:
    """The embedding model, loaded once per process."""
    return SentenceTransformer(config.EMBED_MODEL)


def encode(texts: list[str]) -> list[list[float]]:
    """Unit-length embeddings (so cosine distance = 1 - dot product)."""
    return embedder().encode(
        texts, batch_size=config.EMBED_BATCH_SIZE, normalize_embeddings=True
    ).tolist()


def to_metadata(chunk: Chunk) -> dict:
    """Chroma metadata allows only str/int/float/bool: drop Nones, join lists with commas."""
    meta = {k: v for k, v in chunk.items() if k != "text" and v is not None}
    for field in _LIST_FIELDS:
        meta[field] = ",".join(chunk[field])
    return meta


def from_metadata(text: str, meta: dict) -> Chunk:
    """Inverse of to_metadata: restore Nones and lists."""
    chunk = {**meta, "text": text}
    for field in _OPTIONAL_FIELDS:
        chunk.setdefault(field, None)
    for field in _LIST_FIELDS:
        chunk[field] = [r for r in meta.get(field, "").split(",") if r]
    return chunk  # type: ignore[return-value]


def collection(chroma_dir: Path = config.CHROMA_DIR):
    """The persistent Chroma collection (created on first use, cosine space)."""
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return client.get_or_create_collection(
        config.CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def _add_vectors(chunks: list[Chunk], chroma_dir: Path) -> None:
    """Embed `heading_path + text` and store it with the raw text and all metadata."""
    collection(chroma_dir).add(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=encode([embedding_text(c) for c in chunks]),
        metadatas=[to_metadata(c) for c in chunks],
    )


def _write_bm25(chunks: list[Chunk], bm25_path: Path) -> None:
    """Pickle a BM25 index over every chunk together with the chunks themselves."""
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    corpus = [tokenize(embedding_text(c)) for c in chunks]
    with bm25_path.open("wb") as f:
        pickle.dump({"bm25": BM25Okapi(corpus), "chunks": chunks}, f)


def build_index(
    chunks: list[Chunk],
    chroma_dir: Path = config.CHROMA_DIR,
    bm25_path: Path = config.BM25_PATH,
) -> None:
    """Replace both indexes with ones built from `chunks`."""
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:  # collection did not exist yet
        pass
    _add_vectors(chunks, chroma_dir)
    _write_bm25(chunks, bm25_path)


def add_chunks(
    new_chunks: list[Chunk],
    chroma_dir: Path = config.CHROMA_DIR,
    bm25_path: Path = config.BM25_PATH,
) -> None:
    """Incremental indexing: embed only the new chunks; BM25 is re-fit (cheap, needs global IDF)."""
    _add_vectors(new_chunks, chroma_dir)
    _write_bm25(load_bm25(bm25_path)["chunks"] + new_chunks, bm25_path)


def load_bm25(bm25_path: Path = config.BM25_PATH) -> dict:
    """{'bm25': BM25Okapi, 'chunks': list[Chunk]} as written by build_index."""
    with bm25_path.open("rb") as f:
        return pickle.load(f)


def is_ready(chroma_dir: Path = config.CHROMA_DIR, bm25_path: Path = config.BM25_PATH) -> bool:
    """True when both indexes exist and the vector collection is not empty."""
    return bm25_path.exists() and chroma_dir.exists() and collection(chroma_dir).count() > 0


def vector_search(
    query: str, k: int = 5, chroma_dir: Path = config.CHROMA_DIR
) -> list[tuple[Chunk, float]]:
    """Raw dense search. Returns (chunk, cosine similarity) best first."""
    res = collection(chroma_dir).query(
        query_embeddings=encode([config.EMBED_QUERY_PREFIX + query]), n_results=k
    )
    return [
        (from_metadata(doc, meta), 1.0 - dist)
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
        )
    ]


def bm25_search(
    query: str, k: int = 5, bm25_path: Path = config.BM25_PATH
) -> list[tuple[Chunk, float]]:
    """Raw sparse search. Returns (chunk, BM25 score) best first; zero-score chunks dropped."""
    data = load_bm25(bm25_path)
    scores = data["bm25"].get_scores(tokenize(query))
    ranked = sorted(zip(data["chunks"], scores, strict=True), key=lambda p: p[1], reverse=True)[:k]
    return [(c, float(s)) for c, s in ranked if s > 0]


def _print_hits(label: str, hits: list[tuple[Chunk, float]]) -> None:
    print(f"\n{label}")
    for chunk, score in hits:
        print(f"  {score:7.3f}  {chunk['chunk_id']:10} {chunk['heading_path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build / query the retrieval indexes")
    parser.add_argument("--rebuild", action="store_true", help="re-chunk all documents and rebuild both indexes")
    parser.add_argument("--search", metavar="QUERY", help="print raw vector + BM25 top hits")
    args = parser.parse_args()
    if args.rebuild:
        chunks = build_chunks(load_all_documents())
        write_chunks(chunks)
        build_index(chunks)
        print(f"indexed {len(chunks)} chunks -> {config.CHROMA_DIR}, {config.BM25_PATH}")
    if args.search:
        _print_hits("vector", vector_search(args.search))
        _print_hits("bm25", bm25_search(args.search))
    if not (args.rebuild or args.search):
        parser.print_help()


if __name__ == "__main__":
    main()
