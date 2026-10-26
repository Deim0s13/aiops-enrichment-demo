---
id: KB-RB-022
title: "payments-notify: java.lang.OutOfMemoryError: Java heap space (2.x)"
type: runbook
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-02-10
---

# payments-notify: java.lang.OutOfMemoryError: Java heap space (2.x)

## Purpose

Recover `payments-notify` when the JVM itself runs out of heap and reports `java.lang.OutOfMemoryError: Java heap space`.

## Scope

`payments-notify` 2.x on OpenShift. This runbook is for an out-of-memory error reported by Java. If the container was killed by the kernel (`OOMKilled`, exit code 137) with no Java error, use KB-RB-014 instead.

## Symptoms

- `java.lang.OutOfMemoryError: Java heap space` in the log, usually followed by a stack trace.
- Heap use at, or very near, 100% of the maximum heap for several minutes before the error, with garbage collection running almost continuously.
- Requests time out or fail while the JVM is collecting garbage. The container may keep running in a degraded state rather than restarting.
- If the JVM is set to exit on an out-of-memory error, the container ends with exit code 3, not 137.

## Diagnosis

1. Confirm the Java error in the log and note the time it first appeared.
2. Check that heap use reached its maximum. A heap well short of full points to a different cause.
3. Check whether the JVM wrote a heap dump on the error (`-XX:+HeapDumpOnOutOfMemoryError`).
4. Check for a recent change in traffic, such as a batch run, or a recent deployment.

## Actions

### Level 1

1. If the service is degraded but still running, capture a heap dump and restart the pod with `payments-heapdump-restart`.
2. If the JVM has already written a heap dump on the error, a plain restart is enough; tell Payments Engineering where the dump is.

### Level 2

1. If the heap is genuinely too small for the workload, and the container has headroom, raise the maximum heap through a change request. Keep it at or below about 75% of the container limit.
2. Raise a problem record with Payments Engineering, with the heap dump.

## Verification

- No `OutOfMemoryError` in the log for 30 minutes after recovery.
- Heap use levels off under normal load, with garbage collection pauses back to normal.

## Escalation

Payments Engineering, if the error recurs within a day of a restart.

## Change history

| Date | Change | By |
|---|---|---|
| 2026-02-10 | First version | Payments Platform Operations |
