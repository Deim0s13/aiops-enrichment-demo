---
id: KB-RS-031
title: "Resolution: INC0008812, payments-notify OOMKilled during the month-end statement run"
type: resolution
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-04-02
---

# Resolution: INC0008812, payments-notify OOMKilled during the month-end statement run

## Summary

On 31 March 2026, `payments-notify` 2.3 was killed for exceeding its memory limit four times in 40 minutes during the month-end statement run. Statement-ready notifications were delayed by up to 25 minutes. Priority 2.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 21:05 | Statement run starts; notification volume rises to about eight times normal |
| 21:31 | First `OOMKilled` restart (exit code 137) |
| 21:38 | On-call engineer engaged; second restart |
| 21:52 | Third restart; pod in back-off between restarts |
| 21:58 | Replica added with `payments-scale-out`; restarts slow but continue |
| 22:11 | Fourth restart. Both pods restarted with the statement run finishing; no further kills |

## What we found

- Each container ended with `OOMKilled`, exit code 137. There was no Java `OutOfMemoryError` in the log.
- The log showed `NotificationTemplateCache` warnings, the cache growing steadily and never evicting entries. The statement run uses a different template for each statement type and language, so the cache filled far faster than on a normal day.
- No heap dump was taken: the pods were restarted directly, so Payments Engineering had no evidence of what the cache held.

## Resolution

Restarts and an extra replica carried the service through the statement run. Service recovered at 22:11 when the run finished.

## Root cause and follow-up

- The template cache in 2.x is unbounded: templates loaded during busy periods stay in memory until the pod restarts. Problem PRB0001207 was raised with Payments Engineering; a bounded cache is planned for 2.5.
- KB-RB-014 was updated to take a heap dump before restarting, using `payments-heapdump-restart`, so the next occurrence would preserve the evidence.

## Lessons

- A restart buys time, but the cache refills at the same rate under the same load.
- Take the heap dump first. Restarting without one cost us the evidence the fix needed.
