# demo.aiops

Reusable roles for the demo's AAP content. Playbooks in `automation/` call these roles, so job templates stay thin and the logic is written once.

| Role (planned) | Purpose | Design reference |
|---|---|---|
| `diag_pod_status` | Pod status, restarts and events | Section 5.2 |
| `diag_metrics` | Heap and garbage collection metrics through the Thanos Querier tenancy endpoint | Section 5.2 |
| `diag_changes` | Rollout history and recent change requests | Section 5.2 |
| `diag_logs` | Error-filtered log excerpt with line and byte limits | Section 5.2 |
| `evidence` | Common evidence format and output size limits | Section 5.2 |
| `enrichment_call` (written) | Calls the enrichment service over TLS with its token, checks the answer against design 5.3 (shape, citations, catalogue) and formats the work note (design 5.4); a bad answer fails the step, so the failure branch runs | Sections 5.3 and 5.4 |
| `itsm_worknote` (written) | Marks an incident pending, writes the AI-labelled work note once per revision, or records enrichment as unavailable, as the svc-ai-enrichment identity from the job's credential | Sections 5.4 and 5.5 |
| `remediate_heapdump_restart` | Catalogued level 2 job: capture a heap dump and restart | Section 2.1 |

Every diagnostic role is read-only and returns evidence items in the format defined in section 5.2 of the implementation design.
