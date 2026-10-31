"""Write demo_questions.md from real /ask responses of the running API.

Run: make api   (in another terminal), then: python -m scripts.generate_demo

One question per category: direct, paraphrase, multi-hop, conflict, unanswerable, restricted.
Requests go over HTTP to API_URL with the role's API key, exactly like the UI.
"""
import json

import config
from eval.dataset import load_questions
from ui import api_client

DEMO = [  # (label, question id, role)
    ("Direct", "Q02", "customer"),
    ("Paraphrase", "Q07", "customer"),
    ("Multi-hop", "Q15", "customer"),
    ("Conflict", "Q20", "customer"),
    ("Unanswerable", "Q31", "customer"),
    ("Restricted", "Q40", "customer"),
]
OUTPUT = config.ROOT / "demo_questions.md"


def main() -> None:
    config.require("API_KEYS")
    keys = api_client.role_keys()
    try:
        api_client.health()  # fail early with a clear message if the API is not running
    except api_client.ApiError as exc:
        raise SystemExit(f"{exc}. Start it first in another terminal: make api") from None
    questions = {q["id"]: q for q in load_questions()}
    lines = ["# Demo questions", "", f"Real `/ask` output (LLM: {config.LLM_PROVIDER} / {config.LLM_MODEL}). "
             "Regenerate with `python -m scripts.generate_demo`.", ""]
    for label, qid, role in DEMO:
        q = questions[qid]
        try:
            body = api_client.ask(keys[role], q["question"])
        except api_client.ApiError as exc:  # e.g. 503 when the LLM times out: record it, keep going
            body = {"status": "error", "detail": str(exc)}
        print(f"{qid}: {body.get('status')}")
        lines += [
            f"## {label} ({qid}, role: {role})", "",
            f"**Question:** {q['question']}", "",
            f"**Expected:** `{q['expected_status']}` - {q['expected_answer']}", "",
            f"**Got:** `{body.get('status')}`", "",
            "```json", json.dumps(body, indent=2), "```", "",
        ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
