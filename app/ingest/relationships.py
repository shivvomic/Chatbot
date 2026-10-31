"""Document relationship edges (supersedes / references / conflicts_with) from relationships.json."""
import json
from functools import lru_cache

import config


@lru_cache(maxsize=1)
def load_relationships() -> tuple[dict, ...]:
    """All edges as {'from', 'to', 'type', ...}; empty if the file is missing."""
    if not config.RELATIONSHIPS_PATH.exists():
        return ()
    return tuple(json.loads(config.RELATIONSHIPS_PATH.read_text(encoding="utf-8")))


def edges_between(a: str, b: str, edge_type: str | None = None) -> list[dict]:
    """Edges linking docs `a` and `b` in either direction (optionally of one type)."""
    return [
        e for e in load_relationships()
        if {e["from"], e["to"]} == {a, b} and (edge_type is None or e["type"] == edge_type)
    ]


def supersedes(newer: str, older: str) -> bool:
    """True if a document states that `newer` replaces `older`."""
    return any(e["from"] == newer and e["to"] == older for e in edges_between(newer, older, "supersedes"))


def linked(a: str, b: str) -> bool:
    """True if any relationship edge connects the two documents."""
    return bool(edges_between(a, b))
