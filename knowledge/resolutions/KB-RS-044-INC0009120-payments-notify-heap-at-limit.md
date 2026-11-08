---
id: KB-RS-044
title: "Resolution: INC0009120, payments-notify OOMKilled more often after the heap was raised to the container limit"
type: resolution
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-09-15
---

# Resolution: INC0009120, payments-notify OOMKilled more often after the heap was raised to the container limit

## Summary

On 18 August 2026, `payments-notify` 2.4 was killed for exceeding its memory limit nine times in two hours, on an ordinary business day. Payment confirmations were delayed by up to 15 minutes. Priority 2.

## Background

After INC0008812, change CHG0030418 raised the maximum heap (`JVM_MAX_HEAP`) from 192m to 256m, to give the template cache more room. The container memory limit stayed at 256Mi, so the maximum heap now equalled the limit.

## Timeline (NZDT)

| Time | Event |
|---|---|
| 10:12 | First `OOMKilled` restart (exit code 137), heap at 64% of its maximum |
| 10:40 | Third restart; on-call engineer engaged |
| 11:05 | Heap dump captured and pod restarted with `payments-heapdump-restart` |
| 11:20 | Payments Engineering confirms the template cache holds most of the heap |
| 12:10 | Ninth and last restart; kills stop as volume falls after the midday peak |

## What we found

- Each container ended with `OOMKilled`, exit code 137, while the heap was at 60 to 90% of its maximum: well short of full.
- With the maximum heap equal to the container limit, there was no room left for the JVM's own memory outside the heap: metaspace, thread stacks and buffers. As the template cache grew, the process crossed the container limit long before the heap filled, and the kernel killed it. Java never had the chance to report an `OutOfMemoryError`.
- `NotificationTemplateCache` warnings showed the same steady, unbounded growth as in INC0008812.
- The change had made the kills more frequent, not less: the container now hit its limit at a lower cache size than before.

## Resolution

A heap dump and restart with `payments-heapdump-restart` recovered the service and gave Payments Engineering a heap dump, which confirmed the template cache held most of the heap.

## Root cause and follow-up

- Contributing cause: a maximum heap equal to the container memory limit (CHG0030418).
- Underlying cause: the unbounded template cache, PRB0001207, fix planned for 2.5.
- Change CHG0030455, returning the maximum heap to 192m (about 75% of the limit), is approved and waiting for the next payments release window. Until it is implemented, the service runs with its maximum heap equal to its limit.
- KB-RB-014 was updated: never raise the maximum heap to, or above, the container limit.

## Lessons

- On OpenShift, the container limit has to cover the whole JVM, not just the heap. Raising the heap to the limit removes the margin the JVM needs.
- A kill with the heap well short of full is the signature of this misconfiguration.
