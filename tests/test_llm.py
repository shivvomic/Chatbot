"""Unit tests for the provider wrapper (HTTP is mocked; no real LLM calls)."""
import httpx
import pytest
from pydantic import SecretStr

import config
from app import llm


class FakeResp:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code))

    def json(self) -> dict:
        return self._payload


def _capture(monkeypatch, payload):
    """Replace httpx.post and record what the wrapper sent."""
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return FakeResp(payload)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return seen


def _use(monkeypatch, provider: str, key: str | None = "k") -> None:
    """Select a provider and set (or clear) its key on the settings object."""
    monkeypatch.setattr(config, "LLM_PROVIDER", provider)
    monkeypatch.setattr(config.settings, f"{provider}_api_key", SecretStr(key) if key else None)


def test_openai_compat_request_and_parse(monkeypatch):
    _use(monkeypatch, "groq")
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "pong"}}]})
    assert llm.generate("hi", system="sys", json_mode=True) == "pong"
    assert "groq" in seen["url"]
    assert seen["headers"]["Authorization"] == "Bearer k"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_gemini_request_and_parse(monkeypatch):
    _use(monkeypatch, "gemini")
    seen = _capture(
        monkeypatch, {"candidates": [{"content": {"parts": [{"text": "po"}, {"text": "ng"}]}}]}
    )
    assert llm.generate("hi", system="sys", json_mode=True) == "pong"
    assert "key=" not in seen["url"]  # key travels in a header, never in the URL
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_missing_key_and_unknown_provider(monkeypatch):
    _use(monkeypatch, "openai", key=None)
    assert not llm.is_configured()
    with pytest.raises(RuntimeError):
        llm.generate("hi")
    monkeypatch.setattr(config, "LLM_PROVIDER", "nope")
    with pytest.raises(ValueError):
        llm.generate("hi")


def test_transport_errors_become_llm_error(monkeypatch):
    _use(monkeypatch, "openai")

    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(llm.httpx, "post", boom)
    with pytest.raises(llm.LLMError):
        llm.generate("hi")
    _capture(monkeypatch, {"unexpected": True})  # malformed body -> LLMError, not KeyError
    with pytest.raises(llm.LLMError):
        llm.generate("hi")


def test_rate_limit_is_retried_then_succeeds(monkeypatch):
    _use(monkeypatch, "groq")
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    replies = iter([FakeResp({}, 429, {"retry-after": "3"}), FakeResp({}, 503),
                    FakeResp({"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: next(replies))
    assert llm.generate("hi") == "ok"
    assert sleeps == [3.0, config.LLM_RETRY_BACKOFF_S * 2]  # Retry-After first, then backoff


def test_persistent_rate_limit_becomes_llm_error(monkeypatch):
    _use(monkeypatch, "groq")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: FakeResp({}, 429))
    with pytest.raises(llm.LLMError, match="429"):
        llm.generate("hi")


def test_client_errors_are_not_retried(monkeypatch):
    _use(monkeypatch, "groq")
    calls = []
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: calls.append(1) or FakeResp({}, 400))
    with pytest.raises(llm.LLMError, match="400"):
        llm.generate("hi")
    assert len(calls) == 1
