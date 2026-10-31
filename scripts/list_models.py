"""List the Gemini models your key can use, then test the configured model.

Run: python -m scripts.list_models            (list + test LLM_MODEL from .env)
     python -m scripts.list_models <model>    (list + test that model instead)
Google's error message is printed in full so you can see WHY a call fails.
"""
import sys

import httpx

import config

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def main() -> None:
    headers = {"x-goog-api-key": config.llm_api_key("gemini")}
    r = httpx.get(BASE, params={"pageSize": 200}, headers=headers, timeout=30)
    print("list models: HTTP", r.status_code)
    if r.status_code != 200:
        print(r.text[:800])
        return
    names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    print(", ".join(n for n in names if "flash" in n and "tts" not in n and "image" not in n))

    model = sys.argv[1] if len(sys.argv) > 1 else config.LLM_MODEL
    body = {"contents": [{"role": "user", "parts": [{"text": "Reply with exactly: pong"}]}]}
    t = httpx.post(f"{BASE}/{model}:generateContent", headers=headers, json=body, timeout=60)
    print(f"\ntest {model}: HTTP", t.status_code)
    if t.status_code == 200:
        parts = t.json()["candidates"][0]["content"]["parts"]
        print("reply:", "".join(p.get("text", "") for p in parts).strip(), "-> this model WORKS")
    else:
        print(t.text[:800])


if __name__ == "__main__":
    main()
