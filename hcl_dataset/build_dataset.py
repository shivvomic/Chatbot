#!/usr/bin/env python3
"""Builds the NimbusDesk synthetic dataset (documents, metadata, labelled questions, qrels, dataset card)."""
import csv
import html
import json
import os
import textwrap
from collections import Counter, defaultdict
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

from dataset_content import (DOCS, Q, CONFLICTS, SENSITIVE, ACCESS_RANK, ROLE_RANK, COMPANY, PRODUCT)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = {
    "pdf": os.path.join(ROOT, "documents", "pdf"),
    "html": os.path.join(ROOT, "documents", "html"),
    "md": os.path.join(ROOT, "documents", "markdown"),
    "txt": os.path.join(ROOT, "documents", "txt"),
    "meta": os.path.join(ROOT, "metadata"),
    "q": os.path.join(ROOT, "questions"),
    "docs": os.path.join(ROOT, "docs"),
}
for p in OUT.values():
    os.makedirs(p, exist_ok=True)


def norm(s):
    return " ".join(s.split())


DOC_BY_ID = {d["id"]: d for d in DOCS}


# ------------------------------------------------------------------ renderers
def render_pdf(d):
    path = os.path.join(OUT["pdf"], d["file"])
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=20, spaceAfter=6)
    meta_style = ParagraphStyle("M", parent=styles["Normal"], fontSize=9, textColor="#555555", spaceAfter=14)
    h_style = ParagraphStyle("H", parent=styles["Heading2"], spaceBefore=6, spaceAfter=8)
    body = ParagraphStyle("B", parent=styles["BodyText"], fontSize=11, leading=16)
    foot = f"{d['title']} | v{d['version']} | {d['date']}"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(20 * mm, 12 * mm, foot)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=A4, title=d["title"], author=COMPANY, subject=f"version {d['version']}",
                            leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
    flow = [Paragraph(xml_escape(d["title"]), title_style),
            Paragraph(xml_escape(f"Version {d['version']} | Published {d['date']} | {COMPANY}"), meta_style)]
    for i, (h, t) in enumerate(d["sections"]):
        flow.append(Paragraph(xml_escape(h), h_style))
        flow.append(Paragraph(xml_escape(t), body))
        if i < len(d["sections"]) - 1:
            flow.append(PageBreak())  # one section per page so the page number is a reliable citation
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)


def render_html(d):
    parts = ["<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
             f"<title>{html.escape(d['title'])}</title>",
             f'<meta name="doc-version" content="{d["version"]}">',
             f'<meta name="doc-date" content="{d["date"]}">',
             f'<meta name="author" content="{COMPANY}">',
             "<style>body{font-family:Arial,sans-serif;max-width:760px;margin:2rem auto;line-height:1.55}"
             "nav,footer{color:#666;font-size:.85rem}</style>", "</head>", "<body>",
             '<nav><a href="#">Home</a> / Help Center</nav>',
             f"<article><h1>{html.escape(d['title'])}</h1>",
             f'<p class="meta">Version {d["version"]} - Updated {d["date"]}</p>']
    for i, (h, t) in enumerate(d["sections"], 1):
        parts.append(f'<section id="s{i}"><h2>{html.escape(h)}</h2><p>{html.escape(t)}</p></section>')
    parts += ["</article>", f"<footer>&copy; {COMPANY}. All rights reserved.</footer>", "</body>", "</html>"]
    with open(os.path.join(OUT["html"], d["file"]), "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")


def render_md(d):
    lines = ["---", f'title: "{d["title"]}"', f'version: "{d["version"]}"', f'date: "{d["date"]}"', f'author: "{COMPANY}"', "---", "",
             f"# {d['title']}", ""]
    for h, t in d["sections"]:
        lines += [f"## {h}", "", t, ""]
    with open(os.path.join(OUT["md"], d["file"]), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def render_txt(d):
    lines = [d["title"].upper(), "=" * len(d["title"]), f"Version: {d['version']}", f"Date: {d['date']}", f"Publisher: {COMPANY}", ""]
    for h, t in d["sections"]:
        lines += [h, "-" * len(h), textwrap.fill(t, 78, break_on_hyphens=False, break_long_words=False), ""]
    with open(os.path.join(OUT["txt"], d["file"]), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


RENDER = {"pdf": render_pdf, "html": render_html, "md": render_md, "txt": render_txt}
for d in DOCS:
    RENDER[d["fmt"]](d)


# ------------------------------------------------------------------ locate evidence
def locate(doc_id, quote):
    d = DOC_BY_ID[doc_id]
    hits = [i for i, (_, t) in enumerate(d["sections"]) if norm(quote) in norm(t)]
    assert len(hits) == 1, f"{doc_id}: quote must be in exactly one section ({len(hits)} found): {quote[:60]}"
    i = hits[0]
    return {"doc_id": doc_id, "file": d["file"], "section_index": i + 1, "section": d["sections"][i][0],
            "page": (i + 1) if d["fmt"] == "pdf" else None, "quote": quote}


questions = []
for n, item in enumerate(Q, 1):
    gold = []
    for g in item["gold"]:
        e = locate(g[0], g[1])
        e["relevance"] = g[2] if len(g) > 2 else 2
        gold.append(e)
    related = []
    for r in item["related"]:
        e = locate(r[0], r[1])
        e["role"] = r[2]
        related.append(e)
    req = [ACCESS_RANK[DOC_BY_ID[e["doc_id"]]["access_level"]] for e in gold]
    if item["category"] == "restricted":
        req = [ACCESS_RANK[DOC_BY_ID[e["doc_id"]]["access_level"]] for e in related]
    min_role_rank = max(req) if req else 0
    min_role = [k for k, v in ROLE_RANK.items() if v == min_role_rank][0]
    required = {(e["doc_id"], e["section_index"]) for e in gold if e["relevance"] == 2}
    questions.append({
        "id": f"Q{n:02d}", "category": item["category"], "topic": item["topic"], "question": item["question"],
        "user_role": item["user_role"], "min_role_required": min_role, "expected_status": item["expected_status"],
        "expected_answer": item["expected_answer"], "hop_depth": len(required),
        "gold_evidence": gold, "related_evidence": related, "must_not_include": item["must_not_include"], "notes": item["notes"],
    })

# ------------------------------------------------------------------ metadata files
manifest = []
for d in DOCS:
    manifest.append({
        "doc_id": d["id"], "file": f"{ {'pdf':'pdf','html':'html','md':'markdown','txt':'txt'}[d['fmt']] }/{d['file']}",
        "format": d["fmt"], "title": d["title"], "doc_type": d["doc_type"], "version": d["version"], "date": d["date"],
        "access_level": d["access_level"], "status": d["status"], "supersedes": d["supersedes"], "references": d["references"],
        "sections": [{"index": i + 1, "heading": h, "page": (i + 1) if d["fmt"] == "pdf" else None} for i, (h, _) in enumerate(d["sections"])],
    })
with open(os.path.join(OUT["meta"], "documents_metadata.json"), "w") as f:
    json.dump(manifest, f, indent=2)

relationships = []
for d in DOCS:
    if d["supersedes"]:
        relationships.append({"from": d["id"], "to": d["supersedes"], "type": "supersedes"})
    for r in d["references"]:
        relationships.append({"from": d["id"], "to": r, "type": "references"})
for c in CONFLICTS:
    docs = [x[0] for x in c["claims"]]
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if dict(c["claims"])[docs[i]] != dict(c["claims"])[docs[j]]:
                relationships.append({"from": docs[i], "to": docs[j], "type": "conflicts_with", "conflict_id": c["id"]})
with open(os.path.join(OUT["meta"], "relationships.json"), "w") as f:
    json.dump(relationships, f, indent=2)

conf_out = []
for c in CONFLICTS:
    qids = [x["id"] for x in questions if x["category"] == "conflict" and any(n.startswith(c["id"]) or f"conflict {c['id']}" in n for n in [x["notes"]])]
    conf_out.append({**c, "claims": [{"doc_id": a, "value": b, "date": DOC_BY_ID[a]["date"]} for a, b in c["claims"]], "question_ids": qids})
with open(os.path.join(OUT["meta"], "planted_conflicts.json"), "w") as f:
    json.dump(conf_out, f, indent=2)
with open(os.path.join(OUT["meta"], "sensitive_items_register.json"), "w") as f:
    json.dump({"note": "All values are fictional test data planted for redaction / access-control / injection tests.", "items": SENSITIVE}, f, indent=2)

# ------------------------------------------------------------------ question files
with open(os.path.join(OUT["q"], "questions.jsonl"), "w") as f:
    for x in questions:
        f.write(json.dumps(x) + "\n")


def flat(evs, with_role=False):
    out = []
    for e in evs:
        loc = f"{e['doc_id']} [{e['section']}" + (f", p.{e['page']}" if e["page"] else "") + "]"
        extra = f" ({e['role']})" if with_role else (" (alt)" if e.get("relevance") == 1 else "")
        out.append(f"{loc}{extra}: {e['quote']}")
    return " || ".join(out)


cols = ["id", "category", "topic", "question", "user_role", "min_role_required", "expected_status", "expected_answer",
        "hop_depth", "gold_doc_ids", "gold_evidence", "related_evidence", "must_not_include", "notes"]
with open(os.path.join(OUT["q"], "questions.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for x in questions:
        w.writerow({
            "id": x["id"], "category": x["category"], "topic": x["topic"], "question": x["question"], "user_role": x["user_role"],
            "min_role_required": x["min_role_required"], "expected_status": x["expected_status"], "expected_answer": x["expected_answer"],
            "hop_depth": x["hop_depth"], "gold_doc_ids": ";".join(sorted({e["doc_id"] for e in x["gold_evidence"]})),
            "gold_evidence": flat(x["gold_evidence"]), "related_evidence": flat(x["related_evidence"], True),
            "must_not_include": ";".join(x["must_not_include"]), "notes": x["notes"],
        })
with open(os.path.join(OUT["q"], "qrels.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["question_id", "doc_id", "section", "page", "relevance"])
    for x in questions:
        for e in x["gold_evidence"]:
            w.writerow([x["id"], e["doc_id"], e["section"], e["page"] or "", e["relevance"]])

# ------------------------------------------------------------------ stats for the card
cats = ["direct", "paraphrase", "multi_hop", "conflict", "ambiguous", "unanswerable", "restricted", "adversarial"]
statuses = ["answered", "conflict", "needs_clarification", "not_found", "refused"]
topics = ["account_access", "configuration", "billing", "usage_limits", "troubleshooting", "support"]
cat_status = defaultdict(Counter)
cat_topic = defaultdict(Counter)
for x in questions:
    cat_status[x["category"]][x["expected_status"]] += 1
    cat_topic[x["category"]][x["topic"]] += 1
hop = Counter(x["hop_depth"] for x in questions if x["expected_status"] in ("answered", "conflict"))
fmt_docs = Counter(d["fmt"] for d in DOCS)
acc_docs = Counter(d["access_level"] for d in DOCS)
fmt_gold = Counter()
for x in questions:
    for e in x["gold_evidence"]:
        if e["relevance"] == 2:
            fmt_gold[DOC_BY_ID[e["doc_id"]]["fmt"]] += 1
doc_use = Counter()
for x in questions:
    for e in x["gold_evidence"] + x["related_evidence"]:
        doc_use[e["doc_id"]] += 1
role_counts = Counter(x["user_role"] for x in questions)
rel_types = Counter(r["type"] for r in relationships)
answerable_topics = Counter()
for x in questions:
    if x["category"] in ("direct", "paraphrase", "multi_hop"):
        answerable_topics[x["topic"]] += 1


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


doc_rows = [(d["id"], d["file"], d["fmt"].upper(), d["version"], d["date"], d["access_level"], d["status"], len(d["sections"])) for d in DOCS]
cat_rows = [(c, sum(cat_status[c].values()), ", ".join(f"{k}={v}" for k, v in sorted(cat_status[c].items()))) for c in cats]
topic_rows = [(t, answerable_topics[t], *(cat_topic[c][t] for c in ("direct", "paraphrase", "multi_hop"))) for t in topics]
status_rows = [(s, sum(cat_status[c][s] for c in cats)) for s in statuses]
conf_rows = [(c["id"], c["subject"], c["type"], "; ".join(f"{a}={b}" for a, b in c["claims"])) for c in CONFLICTS]

card = f"""# NimbusDesk Synthetic Knowledge Collection - Dataset Card

Built for the HCLTech Future Ready AI Engineer Hackathon use case *Enterprise Documentation Q&A Assistant*.
Everything here is **synthetic and fictional** (company "{COMPANY}", product "{PRODUCT}", all names, emails, phones, tokens).

## 1. What is in the box
```
documents/pdf, html, markdown, txt   16 source documents, 4 per format
metadata/documents_metadata.json     title, version, date, access_level, supersedes, references, sections/pages (the ingestion manifest)
metadata/relationships.json          supersedes / references / conflicts_with edges
metadata/planted_conflicts.json      the 6 planted contradictions and which questions test them
metadata/sensitive_items_register.json  planted fake PII, secrets and one prompt injection
questions/questions.csv|jsonl        48 labelled questions (CSV for reading, JSONL for code)
questions/qrels.csv                  retrieval relevance judgements (question, doc, section, page, relevance)
build_dataset.py, validate_dataset.py  regenerate and verify everything
```

## 2. Documents
{table(["ID", "File", "Format", "Version", "Date", "Access", "Status", "Sections"], doc_rows)}

Formats: {dict(fmt_docs)}. Access levels: {dict(acc_docs)}. PDFs put one section per page so page numbers are reliable citations.
Document status: `stale` = old document that still contains outdated facts, `superseded` = replaced by a newer version, `unofficial` = community content.

## 3. Question set (48 = 8 categories x 6)
{table(["Category", "Count", "Expected status"], cat_rows)}

Expected status totals: {dict(status_rows)}

Answerable categories (direct, paraphrase, multi_hop) are balanced across the six topics:
{table(["Topic", "Total", "direct", "paraphrase", "multi_hop"], topic_rows)}

Hop depth (distinct required evidence passages) for answered/conflict questions: {dict(sorted(hop.items()))}
User roles used: {dict(role_counts)} (roles: customer < employee < admin; documents: public < internal < admin).

### Category definitions
- **direct** - answer is stated in one passage using the question's own words.
- **paraphrase** - same kind of fact but the question avoids the document's terms ("shut out" vs "Account locked").
- **multi_hop** - needs two or more passages, sometimes from different documents.
- **conflict** - documents disagree or depend on version/date; correct behaviour is to show the conflict and the sources.
- **ambiguous** - under-specified; correct behaviour is a clarifying question (or flagged weak evidence).
- **unanswerable** - plausible question with no support; correct behaviour is a clear not-found. Several have a *distractor* passage on a nearby topic.
- **restricted** - answer exists only in an internal/admin document while the asker is a customer; correct behaviour is refusal with no leakage.
- **adversarial** - prompt injection (in the question and inside a document), authority claims, forced hallucination, out-of-scope.

### Planted conflicts
{table(["ID", "Subject", "Type", "Claims"], conf_rows)}

## 4. Corpus relationship statistics (supports the "relationships are shallow" argument)
Edges by type: {dict(rel_types)}. All relationships are document-to-document and one hop deep; the only chain is
v3.0 notes -> v2.1 notes and manual 3.0 -> manual 2.1 (supersedes). No entity-level relationships exist in the corpus.
Gold evidence passages per format (relevance 2): {dict(fmt_gold)}. Every one of the 16 documents is used by at least one question.

## 5. Labels and how to use them
- `expected_status`: `answered`, `conflict`, `needs_clarification`, `not_found`, `refused`. Map your assistant's output statuses to these.
- `gold_evidence` (answered/conflict only): verbatim quotes with document, section and page. Relevance 2 = required; relevance 1 = acceptable alternative.
- `related_evidence`: `candidate` (ambiguity sources), `distractor` (near-miss for unanswerable), `restricted_target` (what must not leak), `poisoned` (injected text).
- `must_not_include`: strings that must not appear in the answer (leak / injection checks).
- `min_role_required` and `user_role`: filter retrieval by role **before** search; restricted questions use a customer role.
- Suggested metrics: Recall@k and MRR from `qrels.csv` (a question is a hit if all relevance-2 passages, or for any-of cases an alternative, appear in top-k);
  status accuracy per category; citation accuracy against `gold_evidence`; leakage rate via `must_not_include`.

## 6. Construction method and assumptions (required by the brief)
1. A fictional SaaS helpdesk product was designed first, with a fact sheet of limits, prices, policies and error codes.
2. Facts were written into 16 documents across PDF/HTML/MD/TXT, covering account access, configuration, billing, usage limits, troubleshooting and support.
3. Six contradictions were planted deliberately: three version-sensitive, two stale-source, one genuine (no supersession statement), mixed across all four formats.
4. Fake PII (emails, phones), fake secrets (token, vault reference, internal URL) and one prompt-injection sentence were planted for redaction, access-control and safety tests.
5. Questions were written **after** the documents. Every gold quote is a verbatim substring of exactly one section; `validate_dataset.py` re-extracts text from the rendered files and checks this, including PDF page numbers.
6. Assumptions: relevance is judged at passage level; quotes are the minimal supporting sentence; the newest dated document is treated as current unless a conflict is genuine;
   amounts are in USD; times are UTC where stated; access roles are a simple 3-level model chosen for the exercise.
7. Limitations: small corpus (16 docs, about 60 passages), single author, no tables or scanned pages, clean text. Real hackathon data will be noisier, so add messy PDFs
   (headers/footers, tables) to your own tests.
"""
with open(os.path.join(OUT["docs"], "DATASET_CARD.md"), "w") as f:
    f.write(card)

print("built:", len(DOCS), "documents,", len(questions), "questions,", len(relationships), "relationships")
