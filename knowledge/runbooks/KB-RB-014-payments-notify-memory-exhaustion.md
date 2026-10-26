---
id: KB-RB-014
title: "payments-notify: memory exhaustion and OOMKilled restarts (2.x on OpenShift)"
type: runbook
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-09-15
---

# payments-notify: memory exhaustion and OOMKilled restarts (2.x on OpenShift)

## Purpose

Restore `payments-notify` when its container is being killed for exceeding its memory limit, preserve the evidence the Payments Engineering team needs, and stop the restarts recurring.

## Scope

`payments-notify` 2.x, running on OpenShift in the `demo-payments` namespace. Version 1.x ran on virtual machines and is covered by no current runbook: do not apply 1.x guidance to the containerised service.

## Service overview

`payments-notify` sends customers confirmations and alerts for payments, using notification templates it caches in memory. Since July 2026 it delivers them through MessageHub, ACME's SaaS messaging provider, which replaced the in-house mail gateway (CHG0030102). It is a Java service. Its maximum heap is set by the `JVM_MAX_HEAP` environment variable, and its container has a fixed memory limit. Delayed confirmations cause customer contacts within minutes and are reportable if they persist.

## Symptoms

- The container restarts, and its last termination reason is `OOMKilled` with exit code 137. Java does not report an `OutOfMemoryError`: the kernel ends the process first.
- The `PaymentsNotifyOOMKilled` alert fires, often after `PaymentsNotifyHeapHigh`.
- The heap was high, but not full, when the container was killed.
- Repeated warnings from `NotificationTemplateCache` in the log, showing its size growing and stating that entries are never evicted.
- The pod may enter back-off between restarts, so confirmations queue and are sent late.

## Diagnosis

1. Confirm the termination reason: `OOMKilled`, exit code 137, rather than a Java `OutOfMemoryError` (see KB-RB-022) or a failed liveness probe.
2. Compare the maximum heap with the container memory limit. If the maximum heap is close to, or equal to, the limit, the JVM's memory outside the heap (metaspace, threads, buffers) pushes the container over its limit before the heap fills. This is the most common cause.
3. Check the previous container's log for `NotificationTemplateCache` warnings. Steady growth of a fixed amount every few seconds means templates are being loaded and never evicted: a leak in the cache, which a restart only postpones.
4. Check for a rollout or change request in the last 24 hours. A recent change to the heap or memory settings points at the change, not the cache.

## Actions

### Level 1: restore service and keep the evidence

1. Capture a heap dump from the affected pod and restart it, using the catalogued job `payments-heapdump-restart`. The heap dump is what Payments Engineering needs to fix the cache; a restart without one loses it.
2. If restarts continue during business peaks, add a replica with `payments-scale-out` to absorb the load while the cause is fixed.

### Level 2: stop the recurrence

1. Set the maximum heap to about 75% of the container memory limit, leaving room for the JVM's own memory: for a 256 MiB limit, a maximum heap of 192m. Change it through a standard change request, not directly on the cluster.
2. Do not raise the maximum heap to, or above, the container limit. That makes the kill more likely, not less (see KB-RS-044).
3. Raise or update the problem record for the unbounded template cache with Payments Engineering, attaching the heap dump. The permanent fix is a bounded cache, scheduled for 2.5 (PRB0001207).

## Verification

- No further `OOMKilled` restarts for 30 minutes after recovery.
- Heap use levels off below 60% of the maximum heap under normal load.
- `PaymentsNotifyHeapHigh` and `PaymentsNotifyOOMKilled` have cleared.
- The confirmation backlog has drained.

## Escalation

- Payments Platform Operations on-call (ACME Payments On-call) owns recovery.
- Escalate to Payments Engineering if the restarts continue after a heap dump and restart, or if the heap grows without `NotificationTemplateCache` warnings, which points to a different leak.
- Raise a major incident if confirmations are delayed for more than 30 minutes.

## Related documents

- KB-RS-031: resolution of INC0008812, the first occurrence (March 2026).
- KB-RS-044: resolution of INC0009120, made worse by a heap increase (August 2026).
- KB-RB-022: Java `OutOfMemoryError: Java heap space`, a different failure.

## Change history

| Date | Change | By |
|---|---|---|
| 2026-09-15 | Added the heap-to-limit guidance after INC0009120; level 2 actions now go through change requests | Payments Platform Operations |
| 2026-04-02 | Added the template cache diagnosis after INC0008812 | Payments Platform Operations |
| 2025-11-20 | First version for 2.x on OpenShift, replacing KB-RB-009 | Platform Engineering |
