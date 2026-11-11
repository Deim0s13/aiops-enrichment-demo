---
id: KB-RS-046
title: "Resolution: INC0010115, payments-notify: Customer confirmations queuing due to MessageHub 429 errors"
type: resolution
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-11-11
source_incident: INC0010115
drafted_by: acme-knowledge-bot, from the engineer's resolution notes
---

# Resolution: INC0010115, payments-notify: Customer confirmations queuing due to MessageHub 429 errors

## Summary

Payments-notify customer confirmations were queuing due to MessageHub refusing deliveries with HTTP 429 Too Many Requests for client acme-payments-notify. The issue was resolved by pausing sending and escalating to MessageHub, which cleared the incident after 15 minutes, allowing the backlog to drain in 5 minutes.

## Background

The payments-notify service was experiencing issues with MessageHub, a messaging service, which was refusing deliveries with HTTP 429 Too Many Requests errors. This led to a backlog of customer payment confirmations.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 18:53 | Incident opened |
| 05:51 | MessageHub started refusing deliveries with HTTP 429 |
| 05:53 | Backlog grew to over 2,000 notifications |
| 18:53 | Paused notification sending |
| 18:53 | Priority 1 case opened with MessageHub |
| 18:55 | MessageHub cleared the incident |
| 18:55 | Resumed sending and backlog drained |
| 18:55 | Incident resolved |

## What we found

- MessageHub refused deliveries with HTTP 429 Too Many Requests for client acme-payments-notify.
- The backlog grew to over 2,000 customer payment confirmations.
- MessageHub's status page showed an incident in the region with degraded mode, which halves every client's limit.

## Resolution

Paused notification sending to stop retries from counting against the reduced limit. Opened a Priority 1 case with MessageHub through the account administrator, quoting the client ID and the time the 429s began. Resumed sending once MessageHub cleared the incident, allowing the backlog to drain.

## Root cause and follow-up

- Cause: not recorded in the resolution notes.

## Lessons

- Check the MessageHub status page first.
- If MessageHub is in degraded mode, pause sending and wait; do not scale out or ask for a higher limit, which MessageHub does not grant during an incident.
