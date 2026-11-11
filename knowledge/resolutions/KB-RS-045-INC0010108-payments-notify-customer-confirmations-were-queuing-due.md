---
id: KB-RS-045
title: "Resolution: INC0010108, payments-notify: Payments-notify customer confirmations were queuing due to MessageHub refusing deliveries"
type: resolution
service: payments-notify
versions: ["unknown"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-11-11
source_incident: INC0010108
drafted_by: acme-knowledge-bot, from the engineer's resolution notes
---

# Resolution: INC0010108, payments-notify: Payments-notify customer confirmations were queuing due to MessageHub refusing deliveries

## Summary

Payments-notify customer confirmations were queuing due to MessageHub refusing deliveries, causing a backlog of 2,100 notifications. The issue was resolved when MessageHub stopped refusing deliveries, allowing the backlog to drain.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 15:20 NZDT | payments-notify started getting HTTP 429 Too Many Requests from MessageHub |
| 15:20 NZDT | Backlog reached 2,100 notifications, with 11 batches of 600 confirmations each moved to the retry queue after 5 attempts |
| 15:35 NZDT | MessageHub stopped refusing deliveries |
| 15:35 NZDT | Backlog drained over the next few minutes, and the retry queue was sent |
| 15:55 NZDT | Log showed no 429s in the last 5 minutes |

## What we found

- From about 15:20 NZDT on 10 November, payments-notify started getting HTTP 429 Too Many Requests from MessageHub for client acme-payments-notify (limit 3,000 requests a minute).
- The service log showed every retry waiting for MessageHub's Retry-After of 30 seconds, so our retries were behaving correctly and were not adding to the problem.
- MessageHub's status page showed no incident and no degraded mode for our region.
- No changes had been made to payments-notify in the last 24 hours.

## Resolution

Nothing was changed on our side. MessageHub stopped refusing deliveries at about 15:35 NZDT, the backlog drained over the next few minutes, and the retry queue was sent. By 15:55 the log showed no 429s in the last 5 minutes.

## Root cause and follow-up

- MessageHub stopped refusing deliveries at about 15:35 NZDT.

## Lessons

- First check MessageHub's status page for degraded mode, and check our send rate against the 3,000-a-minute limit.
- If our retries are respecting Retry-After, let the backlog drain and keep an eye on the retry queue; a restart will not help.
- If it happens again, ask MessageHub through a change request whether our limit should be raised for peak periods.
