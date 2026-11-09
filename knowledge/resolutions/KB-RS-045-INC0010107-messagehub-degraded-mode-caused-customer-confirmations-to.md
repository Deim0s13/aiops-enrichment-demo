---
id: KB-RS-045
title: "Resolution: INC0010107, payments-notify: MessageHub degraded mode caused customer confirmations to queue"
type: resolution
service: payments-notify
versions: ["unknown"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-11-10
source_incident: INC0010107
drafted_by: acme-knowledge-bot, from the engineer's resolution notes
---

# Resolution: INC0010107, payments-notify: MessageHub degraded mode caused customer confirmations to queue

## Summary

Payments-notify customer confirmations were queuing due to MessageHub refusing deliveries with HTTP 429 errors. The issue was resolved by pausing sending and escalating to MessageHub. Priority 2 incident resolved in 3 minutes.

## Background

The payments-notify service was experiencing issues with MessageHub refusing deliveries, leading to a backlog of customer confirmations.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 09:30 | Incident opened |
| 09:30 | MessageHub degraded mode detected |
| 09:30 | Backlog grew to over 2,000 confirmations |
| 09:30 | Paused notification sending |
| 09:30 | Priority 1 case opened with MessageHub |
| 09:45 | MessageHub cleared the incident |
| 09:45 | Resumed sending and backlog drained |
| 09:33 | Incident resolved |

## What we found

- MessageHub refused deliveries with HTTP 429 for client acme-payments-notify, with Retry-After 30.
- The MessageHub status page showed an incident in our region with degraded mode, which halves every client's limit.
- The backlog grew to over 2,000 customer payment confirmations.

## Resolution

Paused notification sending to stop retries from counting against the reduced limit, opened a Priority 1 case with MessageHub through the account administrator, quoting the client ID and the time the 429s began. Resumed sending once MessageHub cleared the incident.

## Root cause and follow-up

- MessageHub was in degraded mode, which reduced the client's limit and caused HTTP 429 errors.

## Lessons

- Check the MessageHub status page first.
- If MessageHub is in degraded mode, pause sending and wait; do not scale out or ask for a higher limit, which MessageHub does not grant during an incident.
