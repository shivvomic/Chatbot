# Demo questions

Real `/ask` output (LLM: groq / openai/gpt-oss-120b). Regenerate with `python -m scripts.generate_demo`.

## Direct (Q02, role: customer)

**Question:** When are NimbusDesk invoices issued and how many days do customers have to pay them?

**Expected:** `answered` - Invoices are issued on the 1st day of each billing month and payment is due within 14 days of the invoice date.

**Got:** `answered`

```json
{
  "status": "answered",
  "answer": "Invoices are issued on the 1st day of each billing month [D03-s2-c1]. Customers have 14 days from the invoice date to make payment [D03-s2-c1].",
  "citations": [
    {
      "chunk_id": "D03-s2-c1",
      "doc_id": "D03",
      "title": "NimbusDesk Billing and Refund Policy",
      "section": "2. Invoicing and Payment",
      "page": 2,
      "excerpt": "Invoices are issued on the 1st day of each billing month. Payment is due within 14 days of the invoice date. If an invoice is more than 7 days overdue, the workspace becomes read-only until payment is received. A late fee of 1.5 percent per"
    }
  ],
  "confidence": 0.996,
  "conflicts": [],
  "clarifying_question": null,
  "latency_ms": 3319
}
```

## Paraphrase (Q07, role: customer)

**Question:** I typed my password wrong too many times and now I am shut out. How long until I can get back in?

**Expected:** `answered` - Wait 30 minutes or ask an administrator to unlock the account.

**Got:** `answered`

```json
{
  "status": "answered",
  "answer": "The account is locked for 30 minutes after too many failed sign\u2011in attempts [D01-s2-c1] and you can wait that time or have an administrator unlock it [D06-s1-c1]. The lockout rules are unchanged from version 2.1, which also used a 30\u2011minute lockout [D02-s2-c1].",
  "citations": [
    {
      "chunk_id": "D01-s2-c1",
      "doc_id": "D01",
      "title": "NimbusDesk User Manual",
      "section": "2. Signing In and Passwords",
      "page": 2,
      "excerpt": "Users sign in with an email address and password. Passwords must contain at least 8 characters. If you forget your password, select Forgot password on the sign-in page and a reset link is emailed to you. The password reset link is valid for"
    },
    {
      "chunk_id": "D06-s1-c1",
      "doc_id": "D06",
      "title": "NimbusDesk Troubleshooting Guide",
      "section": "I cannot sign in",
      "page": null,
      "excerpt": "If sign-in fails with the message Account locked, wait 30 minutes or ask an administrator to unlock the account from Settings > Members. If the message is Invalid credentials, use Forgot password to reset your password."
    },
    {
      "chunk_id": "D02-s2-c1",
      "doc_id": "D02",
      "title": "NimbusDesk User Manual",
      "section": "2. Signing In and Passwords",
      "page": 2,
      "excerpt": "Passwords must contain at least 8 characters and cannot reuse any of the last 5 passwords. The password reset link is valid for 1 hour. Lockout rules are unchanged from version 2.1. Administrators can set the session timeout between 15 and "
    }
  ],
  "confidence": 0.137,
  "conflicts": [],
  "clarifying_question": null,
  "latency_ms": 2072
}
```

## Multi-hop (Q15, role: customer)

**Question:** Can a Starter workspace use webhooks, and if not, what is the cheapest plan that can and what does it cost?

**Expected:** `answered` - Starter cannot use webhooks; Pro is the cheapest plan with webhooks (up to 10 endpoints) at 29 USD per user per month.

**Got:** `answered`

```json
{
  "status": "answered",
  "answer": "Starter workspaces cannot use webhooks [D07-s3-c1]. Pro workspaces can register up to 10 webhook endpoints, making Pro the cheapest plan that can use webhooks [D07-s3-c1]. Pro costs 29 USD per user per month [D03-s1-c1].",
  "citations": [
    {
      "chunk_id": "D07-s3-c1",
      "doc_id": "D07",
      "title": "NimbusDesk API and Usage Limits",
      "section": "Webhooks",
      "page": null,
      "excerpt": "Pro workspaces can register up to 10 webhook endpoints. Enterprise workspaces can register up to 50. Starter workspaces cannot use webhooks."
    },
    {
      "chunk_id": "D03-s1-c1",
      "doc_id": "D03",
      "title": "NimbusDesk Billing and Refund Policy",
      "section": "1. Plans and Pricing",
      "page": 1,
      "excerpt": "NimbusDesk is offered in three plans billed per user per month: Starter at 12 USD, Pro at 29 USD and Enterprise at 59 USD. Enterprise invoice billing requires a minimum of 25 seats."
    }
  ],
  "confidence": 0.959,
  "conflicts": [],
  "clarifying_question": null,
  "latency_ms": 2247
}
```

## Conflict (Q20, role: customer)

**Question:** What is the maximum attachment size?

**Expected:** `conflict` - Documents disagree: FAQ (2024-09) and 2.1 notes say 25 MB; 3.0 notes and the API limits page say 50 MB. Current value is 50 MB.

**Got:** `conflict`

```json
{
  "status": "conflict",
  "answer": "The maximum attachment size is reported as 25 MB per file in older documents [D05-s2-c1] and 25 MB in a superseded release note [D09-s2-c1]; newer documents state it is 50 MB per file [D10-s2-c1] and 50 MB per file [D07-s4-c1]. Newest source: NimbusDesk API and Usage Limits (version 3.1, 2025-09-15). NimbusDesk 3.0 Release Notes supersedes NimbusDesk 2.1 Release Notes. NimbusDesk Frequently Asked Questions is marked stale. NimbusDesk 2.1 Release Notes is marked superseded.",
  "citations": [
    {
      "chunk_id": "D05-s2-c1",
      "doc_id": "D05",
      "title": "NimbusDesk Frequently Asked Questions",
      "section": "What is the maximum attachment size?",
      "page": null,
      "excerpt": "The maximum attachment size is 25 MB per file."
    },
    {
      "chunk_id": "D09-s2-c1",
      "doc_id": "D09",
      "title": "NimbusDesk 2.1 Release Notes",
      "section": "Limits",
      "page": null,
      "excerpt": "API rate limits in this release are 30 requests per minute for Starter, 100 requests per minute for Pro and 500 requests per minute for Enterprise. The maximum attachment size is 25 MB."
    },
    {
      "chunk_id": "D10-s2-c1",
      "doc_id": "D10",
      "title": "NimbusDesk 3.0 Release Notes",
      "section": "Limits and quotas",
      "page": null,
      "excerpt": "API rate limits are raised to 60 requests per minute for Starter, 300 requests per minute for Pro and 1000 requests per minute for Enterprise. The maximum attachment size is now 50 MB. CSV export now supports up to 10,000 tickets."
    },
    {
      "chunk_id": "D07-s4-c1",
      "doc_id": "D07",
      "title": "NimbusDesk API and Usage Limits",
      "section": "Storage",
      "page": null,
      "excerpt": "Included storage per workspace is 10 GB for Starter, 100 GB for Pro and 1 TB for Enterprise. Maximum attachment size is 50 MB per file."
    }
  ],
  "confidence": 1.0,
  "conflicts": [
    {
      "claim": "Maximum attachment size is 50 MB per file.",
      "chunk_id": "D07-s4-c1",
      "doc_id": "D07",
      "version": "3.1",
      "date": "2025-09-15"
    },
    {
      "claim": "The maximum attachment size is now 50 MB.",
      "chunk_id": "D10-s2-c1",
      "doc_id": "D10",
      "version": "3.0",
      "date": "2025-06-10"
    },
    {
      "claim": "The maximum attachment size is 25 MB per file.",
      "chunk_id": "D05-s2-c1",
      "doc_id": "D05",
      "version": "2.x",
      "date": "2024-09-01"
    },
    {
      "claim": "The maximum attachment size is 25 MB.",
      "chunk_id": "D09-s2-c1",
      "doc_id": "D09",
      "version": "2.1",
      "date": "2024-04-02"
    }
  ],
  "clarifying_question": null,
  "latency_ms": 11360
}
```

## Unanswerable (Q31, role: customer)

**Question:** Does NimbusDesk have a native Salesforce integration?

**Expected:** `not_found` - Not found in the documents; no integration list is provided.

**Got:** `not_found`

```json
{
  "status": "not_found",
  "answer": "I could not find this in the documentation available to you.",
  "citations": [],
  "confidence": 0.0,
  "conflicts": [],
  "clarifying_question": null,
  "latency_ms": 22337
}
```

## Restricted (Q40, role: customer)

**Question:** How long does a database failover to the replica region take?

**Expected:** `refused` - Refuse: failover details are in an admin-level runbook.

**Got:** `refused`

```json
{
  "status": "refused",
  "answer": "I can't answer that with your access level. Please contact an administrator if you need this information.",
  "citations": [],
  "confidence": 0.0,
  "conflicts": [],
  "clarifying_question": null,
  "latency_ms": 2627
}
```
