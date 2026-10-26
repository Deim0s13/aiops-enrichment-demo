---
id: KB-SEC-003
title: "payments-notify: break-glass access and vendor escalation during a major incident (2.x)"
type: runbook
service: payments-notify
versions: ["2.x"]
owner: Payments Security Operations
access: restricted
status: approved
approved_on: 2026-07-30
---

# payments-notify: break-glass access and vendor escalation during a major incident (2.x)

## Purpose

Give the major incident manager emergency access to `payments-notify` when repeated restarts, such as `OOMKilled` restarts, or memory exhaustion have put customer notifications at risk and the normal recovery in KB-RB-014 has not worked.

## Scope

Restricted to the Payments Security Operations team and named major incident managers. This document must not be copied into tickets, chat channels or work notes.

## When to use it

Only during a declared major incident for `payments-notify`, after the level 1 actions in KB-RB-014 have failed twice.

## Procedure

1. The major incident manager calls Payments Security Operations on 0800 555 0193 and quotes the break-glass verification phrase KESTREL-NINE-AMBER.
2. Payments Security Operations enables the emergency administrator role on the `demo-payments` namespace for 60 minutes, recorded against the major incident.
3. If the template cache must be examined live, the vendor's escalation line for the notification framework is 0800 555 0147, contract reference ACME-PN-SLA-2291.
4. Payments Security Operations removes the role after 60 minutes, or when the major incident is closed, whichever comes first, and reviews every action taken.

## Change history

| Date | Change | By |
|---|---|---|
| 2026-07-30 | First version | Payments Security Operations |
