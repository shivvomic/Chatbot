# NimbusDesk Synthetic Knowledge Collection - Dataset Card

Built for the HCLTech Future Ready AI Engineer Hackathon use case *Enterprise Documentation Q&A Assistant*.
Everything here is **synthetic and fictional** (company "Brightwave Systems", product "NimbusDesk", all names, emails, phones, tokens).

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
| ID | File | Format | Version | Date | Access | Status | Sections |
|---|---|---|---|---|---|---|---|
| D01 | user_manual_v2.pdf | PDF | 2.1 | 2024-03-15 | public | superseded | 4 |
| D02 | user_manual_v3.pdf | PDF | 3.0 | 2025-06-10 | public | current | 4 |
| D03 | billing_policy.pdf | PDF | 2025.1 | 2025-04-01 | public | current | 4 |
| D04 | sla_policy.pdf | PDF | 2025.2 | 2025-07-01 | public | current | 4 |
| D05 | faq.html | HTML | 2.x | 2024-09-01 | public | stale | 5 |
| D06 | troubleshooting.html | HTML | 3.0 | 2025-07-15 | public | current | 5 |
| D07 | api_limits.html | HTML | 3.1 | 2025-09-15 | public | current | 4 |
| D08 | sso_setup.html | HTML | 3.0 | 2025-06-20 | public | current | 4 |
| D09 | release_notes_v2_1.md | MD | 2.1 | 2024-04-02 | public | superseded | 4 |
| D10 | release_notes_v3_0.md | MD | 3.0 | 2025-06-10 | public | current | 5 |
| D11 | data_retention.md | MD | 2025.3 | 2025-08-01 | internal | current | 4 |
| D12 | admin_runbook.md | MD | 3.1 | 2025-10-01 | admin | current | 4 |
| D13 | config_guide.txt | TXT | 2.2 | 2024-11-05 | public | stale | 5 |
| D14 | migration_notes.txt | TXT | 3.0 | 2025-07-01 | internal | current | 4 |
| D15 | community_tips.txt | TXT | n/a | 2025-08-20 | public | unofficial | 4 |
| D16 | internal_contacts.txt | TXT | 2025.4 | 2025-09-30 | admin | current | 2 |

Formats: {'pdf': 4, 'html': 4, 'md': 4, 'txt': 4}. Access levels: {'public': 12, 'internal': 2, 'admin': 2}. PDFs put one section per page so page numbers are reliable citations.
Document status: `stale` = old document that still contains outdated facts, `superseded` = replaced by a newer version, `unofficial` = community content.

## 3. Question set (48 = 8 categories x 6)
| Category | Count | Expected status |
|---|---|---|
| direct | 6 | answered=6 |
| paraphrase | 6 | answered=6 |
| multi_hop | 6 | answered=6 |
| conflict | 6 | conflict=6 |
| ambiguous | 6 | needs_clarification=6 |
| unanswerable | 6 | not_found=6 |
| restricted | 6 | refused=6 |
| adversarial | 6 | answered=1, not_found=1, refused=4 |

Expected status totals: {'answered': 19, 'conflict': 6, 'needs_clarification': 6, 'not_found': 7, 'refused': 10}

Answerable categories (direct, paraphrase, multi_hop) are balanced across the six topics:
| Topic | Total | direct | paraphrase | multi_hop |
|---|---|---|---|---|
| account_access | 3 | 1 | 1 | 1 |
| configuration | 3 | 1 | 1 | 1 |
| billing | 3 | 1 | 1 | 1 |
| usage_limits | 3 | 1 | 1 | 1 |
| troubleshooting | 3 | 1 | 1 | 1 |
| support | 3 | 1 | 1 | 1 |

Hop depth (distinct required evidence passages) for answered/conflict questions: {1: 12, 2: 9, 3: 3, 4: 1}
User roles used: {'customer': 47, 'employee': 1} (roles: customer < employee < admin; documents: public < internal < admin).

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
| ID | Subject | Type | Claims |
|---|---|---|---|
| C1 | Password reset link validity | version | D01=24 hours; D02=1 hour; D10=1 hour |
| C2 | Maximum attachment size | stale_source | D05=25 MB; D09=25 MB; D10=50 MB; D07=50 MB |
| C3 | Pro API rate limit | version | D09=100 rpm; D10=300 rpm; D07=300 rpm |
| C4 | Deleted ticket purge period | genuine | D13=30 days; D11=90 days |
| C5 | Enterprise Priority 1 first response | stale_source | D04=1 hour; D05=2 hours |
| C6 | Annual billing discount | date_sensitive | D03=15 percent; D10=20 percent |

## 4. Corpus relationship statistics (supports the "relationships are shallow" argument)
Edges by type: {'supersedes': 2, 'references': 4, 'conflicts_with': 11}. All relationships are document-to-document and one hop deep; the only chain is
v3.0 notes -> v2.1 notes and manual 3.0 -> manual 2.1 (supersedes). No entity-level relationships exist in the corpus.
Gold evidence passages per format (relevance 2): {'pdf': 19, 'md': 10, 'txt': 6, 'html': 12}. Every one of the 16 documents is used by at least one question.

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
