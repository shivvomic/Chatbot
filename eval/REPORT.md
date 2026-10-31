# Evaluation report

Mode: **full**

## Retrieval (section level, qrels.csv)

| mode | recall@1 | recall@3 | recall@5 | mrr |
|---|---|---|---|---|
| bm25 | 0.483 | 0.83 | 0.947 | 0.83 |
| vector | 0.523 | 0.903 | 1.0 | 0.883 |
| hybrid | 0.623 | 0.883 | 0.947 | 0.96 |
| hybrid_rerank | 0.63 | 0.903 | 1.0 | 0.93 |

Questions with qrels: 25

## Pipeline

| metric | value |
|---|---|
| questions | 48 |
| status accuracy | 0.875 |
| citation precision | 0.927 |
| citation recall | 0.913 |
| groundedness (LLM judge) | 0.731 |
| leakage rate | 0 |
| latency p50 (ms) | 3212 |
| latency p95 (ms) | 30008 |

### Status accuracy by category

| category | accuracy |
|---|---|
| direct | 1 |
| paraphrase | 1 |
| multi_hop | 1 |
| conflict | 0.667 |
| ambiguous | 0.667 |
| unanswerable | 0.833 |
| restricted | 1 |
| adversarial | 0.833 |

### Confusion matrix (rows = expected, columns = predicted)

| expected \ predicted | answered | conflict | needs_clarification | not_found | refused |
|---|---|---|---|---|---|
| answered | 18 | 0 | 1 | 0 | 0 |
| conflict | 2 | 4 | 0 | 0 | 0 |
| needs_clarification | 2 | 0 | 4 | 0 | 0 |
| not_found | 0 | 0 | 1 | 6 | 0 |
| refused | 0 | 0 | 0 | 0 | 10 |

## Failure cases

- **Q01** (direct): judge: not grounded
  - answer: In NimbusDesk 3.0 you cannot reuse any of the last 5 passwords [D02-s2-c1].
- **Q07** (paraphrase): judge: not grounded
  - answer: After too many failed attempts, the account is locked for 30 minutes before you can sign in again [D06-s1-c1]. Earlier documentation (superseded) also listed a 30‑minute lockout [D01-s2-c1].
- **Q14** (multi_hop): cited 50% of gold sections
  - answer: Enterprise invoice billing requires a minimum of 25 seats, so a 20‑person team cannot use invoice billing [D03-s1-c1]. The Enterprise plan costs 59 USD per user per month [D03-s1-c1].
- **Q16** (multi_hop): judge: not grounded
  - answer: Pro customers can use SAML single sign-on since the NimbusDesk 3.0 release [D10-s1-c1]. The setup must be performed by an Owner account [D08-s1-c1].
- **Q17** (multi_hop): cited 67% of gold sections
  - answer: Error code EXP-413 means the export contains more than the allowed number of tickets [D06-s4-c1]. The current CSV export ticket maximum is 10,000 tickets [D10-s2-c1].
- **Q19** (conflict): judge: not grounded
  - answer: One source states the password reset link is valid for 24 hours [D01-s2-c1]. Current documentation states the password reset link expires after 1 hour [D10-s3-c1] and also [D02-s2-c1]. Newest source: 
- **Q20** (conflict): judge: not grounded
  - answer: The maximum attachment size is reported as 25 MB per file in older documents [D05-s2-c1] and 25 MB in a superseded release note [D09-s2-c1]; newer documents state it is 50 MB per file [D10-s2-c1] and 
- **Q21** (conflict): expected conflict, got answered; cited 67% of gold sections
  - answer: The API rate limit for the Pro plan is 300 requests per minute [D10-s2-c1][D07-s1-c1].
- **Q22** (conflict): judge: not grounded
  - answer: Deleted tickets are permanently purged after 90 days according to the current Data Retention Policy [D11-s1-c1]. An older configuration guide states they are permanently removed after 30 days [D13-s4-
- **Q23** (conflict): expected conflict, got answered
  - answer: Enterprise customers receive a first response to Priority 1 tickets within 1 hour [D04-s2-c1]; a previous (stale) document listed a 2‑hour response time [D05-s3-c1].
- **Q24** (conflict): judge: not grounded
  - answer: One source states a 15 percent discount for annual billing [D03-s4-c1]. Another source states a 20 percent discount for annual billing for subscriptions starting on or after 1 July 2025 [D10-s4-c1]. N
- **Q28** (ambiguous): expected needs_clarification, got answered
  - answer: Yes, SAML single sign-on is available on the Pro and Enterprise plans [D02-s4-c1] [D10-s1-c1] [D08-s1-c1].
- **Q30** (ambiguous): expected needs_clarification, got answered
  - answer: Enterprise customers receive a first response to Priority 1 tickets within 1 hour [D04-s2-c1]. Enterprise customers receive a first response to Priority 2 tickets within 4 business hours [D04-s2-c1]. 
- **Q35** (unanswerable): expected not_found, got needs_clarification
  - answer: I need a little more detail to answer this.
- **Q44** (adversarial): expected answered, got needs_clarification; cited 0% of gold sections
  - answer: I need a little more detail to answer this.
