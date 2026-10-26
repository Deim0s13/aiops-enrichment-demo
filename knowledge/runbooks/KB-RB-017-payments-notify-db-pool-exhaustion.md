---
id: KB-RB-017
title: "payments-notify: database connection pool exhausted, notifications delayed (2.x)"
type: runbook
service: payments-notify
versions: ["2.x"]
owner: Payments Platform Operations
access: internal
status: approved
approved_on: 2026-05-21
---

# payments-notify: database connection pool exhausted, notifications delayed (2.x)

## Purpose

Restore notification delivery when `payments-notify` cannot get connections to the payments database, and avoid making the database's load worse while doing so.

## Scope

`payments-notify` 2.x on OpenShift, which reads payment events from the payments database through a pool of up to 20 connections per pod.

## Symptoms

- Notifications are delayed or failing, and the confirmation backlog grows.
- The log shows `HikariPool-1 - Connection is not available, request timed out after 30000ms`.
- Liveness probes fail while requests wait for connections, so the container may be restarted. Unlike a memory problem, it ends with exit code 143 (stopped by the kubelet), not 137, and memory use is normal.
- The database shows connections from `payments-notify` at their maximum, often with long-running queries holding them.

## Diagnosis

1. Confirm the connection timeout messages in the log.
2. Check memory: normal heap and container memory rule out the memory runbooks (KB-RB-014, KB-RB-022).
3. Ask the database on-call whether the payments database is slow, locked or failing over.
4. Check for a recent change to queries, pool settings or database maintenance.

## Actions

### Level 1

1. If the database is healthy and a long-running query holds the connections, ask the database on-call to end it. Then restart one `payments-notify` pod at a time.
2. Do not add replicas with `payments-scale-out`: every replica opens its own pool, and more connections make the database's load worse.

### Level 2

1. Fail the payments database over to its standby with `payments-db-failover` only when the database on-call has confirmed the primary has failed. It interrupts every payments service for up to two minutes, so it is never a first step.
2. Raise a problem record with Payments Engineering for the query or pool settings.

## Verification

- No connection timeouts in the log for 15 minutes.
- The confirmation backlog drains.

## Escalation

Database on-call for any database fault; Payments Engineering for query or pool settings.

## Change history

| Date | Change | By |
|---|---|---|
| 2026-05-21 | Added the warning against scaling out | Payments Platform Operations |
| 2025-12-04 | First version for 2.x | Payments Platform Operations |
