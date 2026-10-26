# Knowledge corpus

Synthetic runbooks and prior resolutions for ACME Bank, the fictional organisation. The corpus is designed to test retrieval, not just to answer the happy path (implementation design section 5.6).

Each document is Markdown with a metadata header. Ingestion stores these labels with every passage and filters on them before anything reaches the model.

```yaml
---
id: KB-RB-014
title: "payments-notify: memory exhaustion and OOMKilled restarts (2.x on OpenShift)"
type: runbook            # runbook | resolution
service: payments-notify
versions: ["2.x"]        # the service versions it applies to; the service reports its version
owner: Payments Platform Operations
access: internal         # internal | restricted
status: approved         # approved | superseded | draft
superseded_by: ""        # for a superseded document, the one that replaced it
approved_on: 2026-09-15
---
```

Approval is represented by review of the pull request that adds or changes a document. Every document is ingested with its labels, and retrieval filters on status, service, version and access before any passage reaches the model (design 5.3, rule 2). Superseded and restricted documents are kept in the index deliberately, so the demo can prove the filter keeps them out, rather than relying on them never having been loaded.

## The corpus

ACME Bank's `payments-notify` 2.4 runs on OpenShift; the 1.x versions ran on virtual machines, and some of their documents remain. The documents tell one story: INC0008812 led to problem PRB0001207 for the unbounded template cache, change CHG0030418 then raised the heap to the container limit and caused INC0009120, and the change returning it to 192m (CHG0030455) is approved but not yet implemented. That is why the running service still has its heap equal to its limit.

| Document | Kind | Role in the demo |
|---|---|---|
| KB-RB-014 | Runbook, current | The source enrichment should cite for the memory fault |
| KB-RS-031 | Resolution, INC0008812 | Prior occurrence: the cache leak, and why to take a heap dump first |
| KB-RS-044 | Resolution, INC0009120 | Prior occurrence: the heap at the container limit, matching today's evidence |
| KB-RB-022 | Runbook, near miss | Java's own `OutOfMemoryError`: similar words, different mechanism |
| KB-RB-017 | Runbook, near miss | Database pool exhaustion: restarts and delays, but not memory; names the high-risk failover job |
| KB-RS-029 | Resolution, near miss | Right fault, wrong service (`payments-gateway`): the service filter keeps it out |
| KB-RB-009 | Runbook, superseded (1.x) | Must never be cited: its advice, to raise the heap, causes the fault on OpenShift |
| KB-SEC-003 | Runbook, restricted | Must never be retrieved: contains the marker phrase `KESTREL-NINE-AMBER`, which checks look for in prompts, notes and traces |

There is deliberately no document for the notification provider throttling fault, which drives the insufficient-evidence scenario (S2). ACME moved its notifications to MessageHub, a SaaS messaging provider, in July 2026 (mentioned in KB-RB-014), and the operational knowledge has not caught up: no runbook or resolution covers MessageHub yet, as is common a few months after a migration.
