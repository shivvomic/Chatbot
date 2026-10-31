"""Configuration: fail-fast on missing variables, API key parsing, secrets never echoed."""
import pytest
from pydantic import SecretStr

import config
from app.api.auth import parse_api_keys


def test_require_names_missing_variables(monkeypatch):
    monkeypatch.setattr(config.settings, "api_keys", SecretStr(""))
    with pytest.raises(SystemExit, match="API_KEYS"):
        config.require("API_KEYS")


def test_require_passes_when_set(monkeypatch):
    monkeypatch.setattr(config.settings, "api_keys", SecretStr("k:admin"))
    config.require("API_KEYS")


def test_llm_key_error_names_the_variable(monkeypatch):
    monkeypatch.setattr(config.settings, "groq_api_key", None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        config.llm_api_key("groq")


def test_parse_api_keys():
    assert parse_api_keys("a:customer, b:admin,") == {"a": "customer", "b": "admin"}
    assert parse_api_keys("with:colon:employee") == {"with:colon": "employee"}


@pytest.mark.parametrize("raw", ["Zq9secretvalue:root", "Zq9secretvalue", ":admin"])
def test_parse_api_keys_rejects_bad_entries_without_echoing_them(raw):
    with pytest.raises(SystemExit) as exc:
        parse_api_keys(raw)
    assert "Zq9secretvalue" not in str(exc.value)


def test_secrets_are_masked_in_repr():
    assert "test-secret" not in repr(config.Settings(api_keys=SecretStr("test-secret:admin")))
