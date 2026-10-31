"""Loaders for the labelled evaluation data (questions.jsonl, qrels.csv)."""
import csv
import json
from collections import defaultdict

import config


def load_questions() -> list[dict]:
    """All 48 labelled questions, in file order."""
    lines = config.QUESTIONS_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def load_qrels() -> dict[str, set[tuple[str, str]]]:
    """question_id -> {(doc_id, section)} judged relevant (relevance >= 1)."""
    qrels: dict[str, set[tuple[str, str]]] = defaultdict(set)
    with config.QRELS_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["relevance"]) >= 1:
                qrels[row["question_id"]].add((row["doc_id"], row["section"]))
    return dict(qrels)
