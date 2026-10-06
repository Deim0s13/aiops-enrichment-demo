# demo.aiops

Reusable roles for the demo's AAP content. Playbooks in `automation/` call these roles, so job templates stay thin and the logic is written once.

| Role (planned) | Purpose | Design reference |
|---|---|---|
| `diag_pod_status` | Pod status, restarts and events | Section 5.2 |
| `diag_metrics` | Heap and garbage collection metrics through the Thanos Querier tenancy endpoint | Section 5.2 |
| `diag_changes` | Rollout history and recent change requests | Section 5.2 |
| `diag_logs` | Error-filtered log excerpt with line and byte limits | Section 5.2 |
| `evidence` | Common evidence format and output size limits | Section 5.2 |
| `itsm_worknote` | Idempotent, AI-labelled work note and enrichment fields | Section 5.4 |
| `remediate_heapdump_restart` | Catalogued level 2 job: capture a heap dump and restart | Section 2.1 |

Every diagnostic role is read-only and returns evidence items in the format defined in section 5.2 of the implementation design.
