#!/usr/bin/env python3
"""Independent checks: re-extract text from the rendered files and verify every label and balance rule."""
import json
import os
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCDIR = os.path.join(ROOT, "documents")
errors = []


def norm(s):
    return " ".join(s.split())


def check(cond, msg):
    if not cond:
        errors.append(msg)


manifest = json.load(open(os.path.join(ROOT, "metadata", "documents_metadata.json")))
questions = [json.loads(l) for l in open(os.path.join(ROOT, "questions", "questions.jsonl"))]
by_id = {m["doc_id"]: m for m in manifest}

# ---- extract text per document (per page for PDFs)
text = {}
pages = {}
for m in manifest:
    path = os.path.join(DOCDIR, m["file"])
    check(os.path.exists(path), f"missing file {m['file']}")
    raw = open(path, "rb").read()
    check(all(b < 128 for b in raw) if m["format"] != "pdf" else True, f"non-ASCII bytes in {m['file']}")
    if m["format"] == "pdf":
        reader = PdfReader(path)
        pages[m["doc_id"]] = [norm(p.extract_text() or "") for p in reader.pages]
        text[m["doc_id"]] = " ".join(pages[m["doc_id"]])
        check(len(reader.pages) == len(m["sections"]), f"{m['file']}: pages {len(reader.pages)} != sections {len(m['sections'])}")
    elif m["format"] == "html":
        soup = BeautifulSoup(raw.decode(), "html.parser")
        text[m["doc_id"]] = norm(soup.get_text(" "))
    else:
        text[m["doc_id"]] = norm(raw.decode())

# ---- every evidence quote exists in the rendered file (and on the right PDF page)
n_quotes = 0
for q in questions:
    for key in ("gold_evidence", "related_evidence"):
        for e in q[key]:
            n_quotes += 1
            q_norm = norm(e["quote"])
            check(q_norm in text[e["doc_id"]], f"{q['id']}: quote not found in {e['file']}: {e['quote'][:60]}")
            if e["page"]:
                check(q_norm in pages[e["doc_id"]][e["page"] - 1], f"{q['id']}: quote not on page {e['page']} of {e['file']}")

# ---- structure and balance
cats = Counter(q["category"] for q in questions)
check(len(questions) == 48, f"expected 48 questions, got {len(questions)}")
check(set(cats.values()) == {6} and len(cats) == 8, f"categories not balanced 6x8: {dict(cats)}")
check(Counter(m["format"] for m in manifest) == Counter({"pdf": 4, "html": 4, "md": 4, "txt": 4}), "documents not 4 per format")
check(len({q["id"] for q in questions}) == 48, "duplicate question ids")
check(len({q["question"] for q in questions}) == 48, "duplicate question text")

ans_topics = Counter(q["topic"] for q in questions if q["category"] in ("direct", "paraphrase", "multi_hop"))
check(set(ans_topics.values()) == {3} and len(ans_topics) == 6, f"answerable topics not balanced 3x6: {dict(ans_topics)}")
for c in ("direct", "paraphrase", "multi_hop"):
    t = Counter(q["topic"] for q in questions if q["category"] == c)
    check(set(t.values()) == {1} and len(t) == 6, f"{c}: topics not one each: {dict(t)}")

status_by_cat = {c: {q["expected_status"] for q in questions if q["category"] == c} for c in cats}
exp = {"direct": {"answered"}, "paraphrase": {"answered"}, "multi_hop": {"answered"}, "conflict": {"conflict"},
       "ambiguous": {"needs_clarification"}, "unanswerable": {"not_found"}}
for c, s in exp.items():
    check(status_by_cat[c] == s, f"{c}: unexpected statuses {status_by_cat[c]}")
check(status_by_cat["restricted"] == {"refused"}, "restricted must all be refused")

# ---- per-category rules
ROLE = {"customer": 0, "employee": 1, "admin": 2}
ACC = {"public": 0, "internal": 1, "admin": 2}
for q in questions:
    gold_docs = {e["doc_id"] for e in q["gold_evidence"]}
    if q["expected_status"] in ("answered", "conflict"):
        check(len(q["gold_evidence"]) >= 1, f"{q['id']}: answerable without gold evidence")
        for d in gold_docs:
            check(ROLE[q["user_role"]] >= ACC[by_id[d]["access_level"]], f"{q['id']}: role {q['user_role']} cannot read gold doc {d}")
    if q["category"] == "multi_hop":
        check(q["hop_depth"] >= 2, f"{q['id']}: multi_hop with hop_depth {q['hop_depth']}")
    if q["category"] in ("direct", "paraphrase"):
        check(q["hop_depth"] == 1, f"{q['id']}: {q['category']} hop_depth {q['hop_depth']}")
    if q["category"] == "conflict":
        check(len(gold_docs) >= 2, f"{q['id']}: conflict needs >=2 documents")
    if q["category"] == "restricted":
        tgt = [e for e in q["related_evidence"] if e["role"] == "restricted_target"]
        check(len(tgt) == 1, f"{q['id']}: restricted needs one target")
        for e in tgt:
            check(ROLE[q["user_role"]] < ACC[by_id[e["doc_id"]]["access_level"]], f"{q['id']}: asker is allowed to read the target")
        check(len(q["must_not_include"]) >= 1, f"{q['id']}: no must_not_include")
        # every must_not string really exists in the protected doc
        for s in q["must_not_include"]:
            check(any(norm(s) in text[e["doc_id"]] for e in tgt), f"{q['id']}: must_not '{s}' not in target doc")
    if q["category"] == "unanswerable":
        check(not q["gold_evidence"], f"{q['id']}: unanswerable has gold evidence")

# ---- unanswerable questions must really be unanswerable: key terms absent from the corpus
corpus = " ".join(text.values()).lower()
for term in ["salesforce", "wh-500", "hardware security key", "euro", "phone support", "android"]:
    check(term not in corpus, f"corpus unexpectedly contains '{term}'")
check(not re.search(r"\bagents? (are|is) (limited|capped)|maximum number of agents|up to \d+ agents", corpus), "corpus states an agent cap")

# ---- planted conflicts: claimed values really differ and appear in the documents
conf = json.load(open(os.path.join(ROOT, "metadata", "planted_conflicts.json")))
check(len(conf) == 6, "expected 6 planted conflicts")
conf_q = Counter()
for c in conf:
    check(len({x["value"] for x in c["claims"]}) >= 2, f"{c['id']}: claims do not differ")
    conf_q.update(c["question_ids"])
check(set(conf_q.values()) == {1} and len(conf_q) == 6, f"conflict questions not mapped 1:1 -> {dict(conf_q)}")

# ---- sensitive items planted, and every document is used by some question
for s in json.load(open(os.path.join(ROOT, "metadata", "sensitive_items_register.json")))["items"]:
    check(norm(s["value"]) in text[s["doc"]], f"sensitive item missing: {s['value']}")
used = {e["doc_id"] for q in questions for k in ("gold_evidence", "related_evidence") for e in q[k]}
check(used == set(by_id), f"documents never used by a question: {set(by_id) - used}")

# ---- qrels consistent with jsonl
import csv
qrels = list(csv.DictReader(open(os.path.join(ROOT, "questions", "qrels.csv"))))
n_gold = sum(len(q["gold_evidence"]) for q in questions)
check(len(qrels) == n_gold, f"qrels rows {len(qrels)} != gold passages {n_gold}")

if errors:
    print("VALIDATION FAILED")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print(f"ALL CHECKS PASSED | {len(manifest)} docs | {len(questions)} questions | {n_quotes} evidence quotes verified in rendered files")
print("categories:", dict(cats))
print("answerable topics:", dict(ans_topics))
print("hop depth:", dict(sorted(Counter(q['hop_depth'] for q in questions if q['expected_status'] in ('answered', 'conflict')).items())))
