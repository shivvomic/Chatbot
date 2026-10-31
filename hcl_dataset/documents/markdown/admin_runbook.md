---
title: "NimbusDesk Admin Runbook"
version: "3.1"
date: "2025-10-01"
author: "Brightwave Systems"
---

# NimbusDesk Admin Runbook

## Emergency lockout recovery

If an Owner is locked out, an admin console operator can issue a one-time recovery code from the internal console at https://console.brightwave.example/recovery. Recovery codes expire after 15 minutes.

## Credentials and secrets

The break-glass service account is svc-breakglass. Its temporary password is stored in vault entry BW-VAULT-0042 and is rotated every 30 days. Example staging token used in test scripts: NB-STG-7F3A9C21D84E5B60.

## Database failover

Failover to the replica region takes about 12 minutes. Only the on-call engineer may trigger it. The on-call contact list is kept in the internal contacts file.

## Feature flags

The AI suggested replies beta is controlled by the flag ai_replies_beta and is enabled for Enterprise workspaces only.
