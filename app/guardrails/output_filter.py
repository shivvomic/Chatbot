"""Output scan: block answers that contain PII / secret patterns or planted sensitive values."""
import json
import re
from functools import lru_cache

import config
from app.guardrails.input_guard import is_instruction_like

_PATTERNS = [(name, re.compile(p)) for name, p in config.REDACTION_PATTERNS.items()]


@lru_cache(maxsize=1)
def _planted_values() -> tuple[tuple[str, str], ...]:
    """(kind, value) for every item in sensitive_items_register.json, lower-cased."""
    if not config.SENSITIVE_REGISTER_PATH.exists():
        return ()
    items = json.loads(config.SENSITIVE_REGISTER_PATH.read_text(encoding="utf-8"))["items"]
    return tuple((i["kind"], i["value"].lower()) for i in items)


def find_leaks(text: str) -> list[str]:
    """Kinds of sensitive content found in `text` (empty list = clean). Values are never returned."""
    found = [name.lower() for name, pattern in _PATTERNS if pattern.search(text)]
    lowered = text.lower()
    found += [kind for kind, value in _planted_values() if value in lowered]
    if is_instruction_like(text):
        found.append("instruction_text")
    return sorted(set(found))
