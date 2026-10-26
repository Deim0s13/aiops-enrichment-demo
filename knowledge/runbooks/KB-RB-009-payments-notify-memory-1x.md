---
id: KB-RB-009
title: "payments-notify: high memory and slow notifications (1.x)"
type: runbook
service: payments-notify
versions: ["1.x"]
owner: Payments Platform Operations
access: internal
status: superseded
superseded_by: KB-RB-014
approved_on: 2023-06-12
---

# payments-notify: high memory and slow notifications (1.x)

## Purpose

Recover `payments-notify` when it runs short of memory and notifications slow down or stop.

## Scope

`payments-notify` 1.x on the payments application servers (`pnapp01` to `pnapp04`), installed in `/opt/acme/payments-notify` and run as the `payments-notify` systemd service.

## Symptoms

- Notifications are sent slowly, or the service stops sending them.
- The memory monitor raises a "payments-notify memory above 85%" alert.
- The application log (`/var/log/acme/payments-notify/app.log`) shows long garbage collection pauses or `java.lang.OutOfMemoryError: Java heap space`.

## Diagnosis

1. Check the service's memory with `systemctl status payments-notify` and `top`.
2. Look in the application log for `OutOfMemoryError` and for garbage collection pauses of more than a second.
3. Check how much memory the server has free. The application servers have 16 GB, so there is normally room to give the service more.

## Actions

1. Raise the maximum heap. Edit `/etc/sysconfig/payments-notify` and change `-Xmx512m` to `-Xmx1g`.
2. Restart the service on one server at a time: `systemctl restart payments-notify`. Wait for it to report healthy before moving to the next server.
3. If memory use climbs again within a week, raise the maximum heap further, up to `-Xmx2g`, and tell Payments Engineering.

## Verification

- The memory alert clears.
- Notifications are being sent within a minute of the payment.
- No `OutOfMemoryError` in the log for 24 hours.

## Escalation

Payments Engineering, if the service still runs out of memory at `-Xmx2g`.

## Change history

| Date | Change | By |
|---|---|---|
| 2023-06-12 | Raised the default advice from 768m to 1g | Payments Platform Operations |
| 2021-09-03 | First version | Payments Platform Operations |
