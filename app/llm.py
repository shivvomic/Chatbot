"""Provider wrapper: one generate() for Gemini / OpenAI / Groq, chosen by LLM_PROVIDER.

Plain HTTP via httpx (no SDKs). OpenAI and Groq share the OpenAI chat-completions format;
Gemini uses its own generateContent format.
"""
import time

import httpx

import config

_OPENAI_COMPAT_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRY_STATUSES = {429, 500, 502, 503, 504}  # rate limited or provider overloaded: worth retrying


class LLMError(RuntimeError):
    """The provider could not be reached or returned an unusable reply."""


def _post(url: str, headers: dict, body: dict, timeout: float) -> httpx.Response:
    """POST with retries on 429 / 5xx. Waits Retry-After when given, else a linear backoff."""
    for attempt in range(config.LLM_RETRIES + 1):
        resp = httpx.post(url, headers=headers, json=body, timeout=timeout)
        if resp.status_code not in _RETRY_STATUSES or attempt == config.LLM_RETRIES:
            break
        retry_after = resp.headers.get("retry-after", "")
        if retry_after.replace(".", "", 1).isdigit():  # provider told us how long to wait
            wait = float(retry_after)
        else:
            wait = config.LLM_RETRY_BACKOFF_S * (attempt + 1)
        time.sleep(min(wait, config.LLM_RETRY_MAX_WAIT_S))
    resp.raise_for_status()
    return resp


def _openai_compat(provider: str, prompt: str, system: str, json_mode: bool, timeout: float) -> str:
    """Call an OpenAI-compatible chat endpoint and return the reply text."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    body: dict = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": config.LLM_TEMPERATURE,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}  # prompt must mention "JSON"
    resp = _post(
        _OPENAI_COMPAT_URLS[provider],
        {"Authorization": f"Bearer {config.llm_api_key(provider)}"},
        body,
        timeout,
    )
    return resp.json()["choices"][0]["message"]["content"]


def _gemini(prompt: str, system: str, json_mode: bool, timeout: float) -> str:
    """Call Gemini generateContent and return the concatenated text parts."""
    gen_config: dict = {"temperature": config.LLM_TEMPERATURE}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = _post(
        _GEMINI_URL.format(model=config.LLM_MODEL),
        {"x-goog-api-key": config.llm_api_key("gemini")},  # header, never the URL
        body,
        timeout,
    )
    parts = resp.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def generate(prompt: str, system: str = "", json_mode: bool = False, timeout: float | None = None) -> str:
    """Return the model's text reply. With json_mode=True the reply is a JSON string.

    `timeout` (seconds) overrides LLM_TIMEOUT_S for quick calls such as the scope check.

    Raises RuntimeError if the provider's API key is missing, ValueError for an unknown
    provider and LLMError for network / HTTP / response-format failures.
    """
    provider = config.LLM_PROVIDER
    timeout = timeout or config.LLM_TIMEOUT_S
    try:
        if provider == "gemini":
            return _gemini(prompt, system, json_mode, timeout)
        if provider in _OPENAI_COMPAT_URLS:
            return _openai_compat(provider, prompt, system, json_mode, timeout)
    except httpx.HTTPStatusError as exc:  # status only: the body may echo the request
        raise LLMError(f"{provider} returned HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"{provider} call failed: {type(exc).__name__}") from None
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}' (use gemini | openai | groq)")


def is_configured() -> bool:
    """True when the selected provider has an API key (used to skip LLM-only work)."""
    try:
        config.llm_api_key(config.LLM_PROVIDER)
    except RuntimeError:
        return False
    return True
