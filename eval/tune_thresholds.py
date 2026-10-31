"""Tune the pre-LLM gates on questions.jsonl (retrieval only, no LLM calls).

Run: python -m eval.tune_thresholds

Gates are applied in pipeline order (restricted -> vague -> not_found). For each gate it
prints how many questions of the target status it catches and how many others it would
wrongly catch, then suggests the middle of the range of values that catch the most targets
with zero false positives (a margin on both sides). Copy the suggestions into config.py.
"""
from dataclasses import dataclass

import config
from app.guardrails.input_guard import classify, content_words, is_secret_request
from app.retrieval.search import can_read, search
from eval.dataset import load_questions


@dataclass
class Probe:
    qid: str
    expected: str
    top: float  # best score the asking role can read
    unfiltered_top: float  # best score over all documents
    unfiltered_readable: bool  # can the role read that best overall chunk?
    words: int  # content words in the question
    pre_refused: bool  # stopped by the input guard / secret rule before retrieval


def probe(q: dict) -> Probe:
    hits = search(q["question"], q["user_role"])
    best = search(q["question"], "admin", top_n=1)
    return Probe(
        qid=q["id"], expected=q["expected_status"],
        top=hits[0].score if hits else 0.0,
        unfiltered_top=best[0].score if best else 0.0,
        unfiltered_readable=bool(best) and can_read(q["user_role"], best[0].chunk),
        words=len(content_words(q["question"])),
        pre_refused=classify(q["question"]).label != "allowed" or is_secret_request(q["question"]),
    )


def _best(candidates: list, caught, target: str, probes: list[Probe]) -> tuple:
    """((value, hits, false positives), all rows): middle of the best zero-false-positive range."""
    rows = []
    for value in candidates:
        flagged = [p for p in probes if caught(p, value)]
        hits = sum(p.expected == target for p in flagged)
        rows.append((value, hits, len(flagged) - hits))
    safe = [r for r in rows if r[2] == 0] or rows
    top_hits = max(r[1] for r in safe)
    best = [r for r in safe if r[1] == top_hits]
    return best[len(best) // 2], rows


def main() -> None:
    probes = [probe(q) for q in load_questions()]
    live = [p for p in probes if not p.pre_refused]  # what reaches the gates

    def restricted(p: Probe, weak_score: float) -> bool:
        return not p.unfiltered_readable and p.unfiltered_top >= config.RESTRICTED_MIN_SCORE and p.top < weak_score

    weak, _ = _best([0.01, 0.02, 0.05, 0.1, 0.2, 0.3], restricted, "refused", live)
    live = [p for p in live if not restricted(p, weak[0])]
    vague, _ = _best([1, 2, 3], lambda p, v: p.words <= v, "needs_clarification", live)
    gated = [p for p in live if p.words > vague[0]]  # not_found gate runs after the vague gate
    not_found, rows = _best(
        [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05],
        lambda p, v: p.top < v, "not_found", gated,
    )

    print("not_found threshold (value, caught not_found, wrongly caught):")
    for row in rows:
        print(f"  {row[0]:<6} {row[1]:>2} {row[2]:>2}")
    print("\nSuggested config values (current in brackets):")
    print(f"  NOT_FOUND_THRESHOLD     = {not_found[0]}  [{config.NOT_FOUND_THRESHOLD}]  catches {not_found[1]}")
    print(f"  VAGUE_MAX_CONTENT_WORDS = {vague[0]}  [{config.VAGUE_MAX_CONTENT_WORDS}]  catches {vague[1]}")
    print(f"  RESTRICTED_WEAK_SCORE   = {weak[0]}  [{config.RESTRICTED_WEAK_SCORE}]  catches {weak[1]}")
    print("\nPer-question probe (expected, top, unfiltered top, readable, words):")
    for p in probes:
        flag = " pre-refused" if p.pre_refused else ""
        print(f"  {p.qid} {p.expected:<20} {p.top:.3f} {p.unfiltered_top:.3f} "
              f"{p.unfiltered_readable!s:<5} {p.words}{flag}")


if __name__ == "__main__":
    main()
