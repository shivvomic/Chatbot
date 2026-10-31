"""List the Groq models your key can use, then test one.

Run: python -m scripts.list_groq_models            (list + test LLM_MODEL from .env)
     python -m scripts.list_groq_models <model>    (list + test that model)
Groq's error message is printed in full so you can see WHY a call fails.
"""
import sys

import httpx

import config

BASE = "https://api.groq.com/openai/v1"


def main() -> None:
    headers = {"Authorization": f"Bearer {config.llm_api_key('groq')}"}
    r = httpx.get(f"{BASE}/models", headers=headers, timeout=30)
    print("list models: HTTP", r.status_code)
    if r.status_code != 200:
        print(r.text[:800])
        return
    skip = ("whisper", "tts", "guard", "playai", "orpheus", "distil")
    ids = sorted(m["id"] for m in r.json().get("data", []) if m.get("active", True))
    print("chat models:")
    for i in ids:
        if not any(s in i.lower() for s in skip):
            print("  ", i)

    model = sys.argv[1] if len(sys.argv) > 1 else config.LLM_MODEL
    body = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
            "temperature": 0}
    t = httpx.post(f"{BASE}/chat/completions", headers=headers, json=body, timeout=60)
    print(f"\ntest {model}: HTTP", t.status_code)
    if t.status_code == 200:
        print("reply:", t.json()["choices"][0]["message"]["content"].strip(), "-> this model WORKS")
    else:
        print(t.text[:800])


if __name__ == "__main__":
    main()
