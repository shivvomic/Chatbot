"""API-key authentication: the X-API-Key header decides the caller's role.

Keys come from the API_KEYS env var ("key1:customer,key2:admin"). The role is taken from the
key only - never from the request body - so a caller cannot promote itself.
"""
import hmac
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status

import config

API_KEY_HEADER = "X-API-Key"


def parse_api_keys(raw: str) -> dict[str, str]:
    """'k1:customer,k2:admin' -> {'k1': 'customer', 'k2': 'admin'}; rejects unknown roles."""
    keys: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        key, sep, role = entry.rpartition(":")
        if not sep or not key or role not in config.ROLE_RANK:
            raise SystemExit(f"API_KEYS entry #{len(keys) + 1} must look like '<key>:<{'|'.join(config.ROLE_RANK)}>'")
        keys[key] = role
    return keys


@lru_cache(maxsize=1)
def api_keys() -> dict[str, str]:
    """Parsed API_KEYS, cached for the process lifetime."""
    return parse_api_keys(config.settings.api_keys.get_secret_value())


def role_for_key(presented: str) -> str | None:
    """Role of a presented key, compared in constant time against every configured key."""
    role = None
    for key, key_role in api_keys().items():
        if hmac.compare_digest(key.encode(), presented.encode()):
            role = key_role
    return role


def current_role(x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER)) -> str:
    """FastAPI dependency: the authenticated role, or 401."""
    role = role_for_key(x_api_key or "")
    if role is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key",
                            headers={"WWW-Authenticate": API_KEY_HEADER})
    return role


def require_role(minimum: str):
    """Dependency factory: 403 unless the caller's role rank is at least `minimum`."""
    def check(role: str = Depends(current_role)) -> str:
        if config.ROLE_RANK[role] < config.ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the {minimum} role")
        return role
    return check
