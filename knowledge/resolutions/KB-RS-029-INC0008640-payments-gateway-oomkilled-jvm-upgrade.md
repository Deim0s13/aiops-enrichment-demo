---
id: KB-RS-029
title: "Resolution: INC0008640, payments-gateway OOMKilled after the Java 21 upgrade"
type: resolution
service: payments-gateway
versions: ["5.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-03-04
---

# Resolution: INC0008640, payments-gateway OOMKilled after the Java 21 upgrade

## Summary

On 24 February 2026, after `payments-gateway` 5.2 moved from Java 17 to Java 21, its containers were killed for exceeding their memory limit within an hour of each start. Card authorisations were retried by the card network and none were lost. Priority 2.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 09:30 | `payments-gateway` 5.2 rolled out on the Java 21 image |
| 10:14 | First `OOMKilled` restart (exit code 137), heap at about 50% of its maximum |
| 10:35 | On-call engineer engaged; restarts every 40 to 60 minutes |
| 11:20 | Rolled back to the Java 17 image under emergency change CHG0029977; kills stop |

## What we found

- Each container ended with `OOMKilled`, exit code 137. The heap was at about 50% of its maximum when it was killed.
- The new Java version used noticeably more memory outside the heap, mostly metaspace and code cache, because of the larger set of classes the gateway loads at start. The container limit had not been changed with the upgrade.
- There was no growth in any cache; memory rose quickly after start and then levelled off just above the limit.

## Resolution

The deployment was rolled back to the Java 17 image under emergency change CHG0029977, and the kills stopped. The upgrade was redone a week later with the container memory limit raised from 1Gi to 1.5Gi, and metaspace capped with `-XX:MaxMetaspaceSize`.

## Root cause and follow-up

- Root cause: Java 21 needs more memory outside the heap for the gateway's classes, and the container limit was not resized with the upgrade.
- The upgrade was redone on 3 March 2026 under CHG0030021, with the limit raised to 1.5Gi and metaspace capped. No kills since.
- The Java upgrade checklist now includes rechecking container limits under load.

## Lessons

- Size the container limit for the whole JVM, and recheck it when the Java version changes.
- Memory that rises quickly after start and then levels off points to the runtime, not to a leak in the application.
