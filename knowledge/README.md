# Knowledge corpus

Synthetic runbooks and prior resolutions for ACME Bank, the fictional organisation. The corpus is designed to test retrieval, not just to answer the happy path (implementation design section 5.6).

Each document is Markdown with a metadata header. Ingestion stores these labels with every passage and filters on them before anything reaches the model.

```yaml
---
id: KB-RB-014
title: payments-notify heap exhaustion
type: runbook            # runbook | resolution
service: payments-notify
versions: ["2.x"]
owner: platform-operations
access: internal         # internal | restricted
status: approved         # approved | superseded | draft
approved_on: 2026-10-01
---
```

Approval is represented by review of the pull request that adds or changes a document. Only documents with `status: approved` are ingested for retrieval; superseded and restricted documents are kept deliberately, so the demo can prove they are never cited.
