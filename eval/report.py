"""Render evaluation results (the dict from run_eval.run_evaluation) as eval/REPORT.md."""
from pathlib import Path


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join("-" if v is None else str(v) for v in row) + " |" for row in rows]


def render_report(results: dict) -> str:
    """Markdown with retrieval ablation, pipeline metrics, confusion matrix and failures."""
    out = ["# Evaluation report", "", f"Mode: **{results['mode']}**", "", "## Retrieval (section level, qrels.csv)", ""]
    retrieval = results["retrieval"]
    keys = [k for k in next(iter(retrieval.values())) if k != "n"]
    out += _table(["mode", *keys], [[m, *(v[k] for k in keys)] for m, v in retrieval.items()])
    out += ["", f"Questions with qrels: {next(iter(retrieval.values()))['n']}"]

    pipe = results.get("pipeline")
    if not pipe:
        out += ["", "_Pipeline metrics skipped (`--fast`)._"]
        return "\n".join(out) + "\n"

    out += ["", "## Pipeline", ""]
    out += _table(["metric", "value"], [
        ["questions", pipe["n"]],
        ["status accuracy", pipe["status_accuracy"]],
        ["citation precision", pipe["citation_precision"]],
        ["citation recall", pipe["citation_recall"]],
        ["groundedness (LLM judge)", pipe["groundedness"] if results.get("judge") else "skipped"],
        ["leakage rate", pipe["leakage_rate"]],
        ["latency p50 (ms)", pipe["latency_p50_ms"]],
        ["latency p95 (ms)", pipe["latency_p95_ms"]],
    ])
    out += ["", "### Status accuracy by category", ""]
    out += _table(["category", "accuracy"], [[c, a] for c, a in pipe["status_accuracy_by_category"].items()])
    out += ["", "### Confusion matrix (rows = expected, columns = predicted)", ""]
    statuses = list(pipe["confusion_matrix"])
    out += _table(["expected \\ predicted", *statuses],
                  [[e, *(pipe["confusion_matrix"][e][p] for p in statuses)] for e in statuses])
    out += ["", "## Failure cases", ""]
    failures = results.get("failures", [])
    if not failures:
        out.append("None.")
    for f in failures:
        out.append(f"- **{f['id']}** ({f['category']}): {'; '.join(f['reasons'])}")
        if f["answer"]:
            out.append(f"  - answer: {f['answer']}")
    return "\n".join(out) + "\n"


def write_report(results: dict, path: Path) -> None:
    path.write_text(render_report(results), encoding="utf-8")
