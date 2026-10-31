"""HTTP client the Streamlit UI uses. The UI never imports the pipeline: it only calls the API."""
import httpx

import config


class ApiError(RuntimeError):
    """Non-2xx response; message is the API's `detail`."""


def role_keys() -> dict[str, str]:
    """role -> API key, from the same API_KEYS variable the API reads (first key per role)."""
    keys: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in config.settings.api_keys.get_secret_value().split(","))):
        key, _, role = entry.rpartition(":")
        keys.setdefault(role, key)
    return keys


def _request(method: str, path: str, key: str | None, **kwargs) -> dict | list:
    headers = {"X-API-Key": key} if key else {}
    try:
        resp = httpx.request(method, f"{config.settings.api_url}{path}", headers=headers,
                             timeout=config.UI_REQUEST_TIMEOUT_S, **kwargs)
    except httpx.HTTPError as exc:
        raise ApiError(f"API unreachable at {config.settings.api_url} ({type(exc).__name__})") from None
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"{resp.status_code}: {detail}")
    return resp.json()


def health() -> dict:
    return _request("GET", "/health", None)


def ask(key: str, question: str) -> dict:
    return _request("POST", "/ask", key, json={"question": question})


def documents(key: str) -> list:
    return _request("GET", "/documents", key)


def upload(key: str, name: str, content: bytes, access_level: str) -> dict:
    return _request("POST", "/upload", key, data={"access_level": access_level},
                    files={"file": (name, content)})


def evaluate(key: str, fast: bool, judge: bool) -> dict:
    return _request("POST", "/evaluate", key, json={"fast": fast, "judge": judge})
