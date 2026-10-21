# demo.aiops

Reusable roles for the demo's AAP content. Playbooks in `automation/` call these roles, so job templates stay thin and the logic is written once.

| Role | Purpose | Design reference |
|---|---|---|
| `diag_pod_status` (written) | Pod status, restarts, last terminations and recent warning events | Section 5.2 |
| `diag_metrics` (written) | Heap, container memory and restarts through the Thanos Querier tenancy endpoint; reports the absence of garbage collection metrics | Section 5.2 |
| `diag_changes` (written) | Rollout history, running resources and JVM settings, and recent change requests for the configuration item | Section 5.2 |
| `diag_logs` (written) | Warnings and errors from the previous (or current) container log, with line and byte limits; repeated messages collapsed into one entry with a count, a time range and the first and last values | Section 5.2 |
| `evidence` (written) | Runs one diagnostic for the incident's configuration item, found in the service map; turns a failure into a gap item; applies the size limits and publishes the evidence as a workflow artefact. Diagnostics call the cluster with the job's time-limited, read-only cluster credential | Section 5.2; DD20 |
| `enrichment_call` (written) | Calls the enrichment service over TLS with its token, checks the answer against design 5.3 (shape, citations, catalogue) and formats the work note (design 5.4); a bad answer fails the step, so the failure branch runs | Sections 5.3 and 5.4 |
| `itsm_alert` (written) | Integration stand-in: raises or updates one ServiceNow incident per service and incident family from Alertmanager alerts, as svc-monitoring. Only a critical alert raises one. Later alerts become work notes with an occurrence count, a more severe alert raises the priority, a cleared alert is noted, and a repeated notification changes nothing | Section 2.1, step 1; DD19 |
| `itsm_worknote` (written) | Marks an incident pending, writes the AI-labelled work note once per revision, or records enrichment as unavailable, as the svc-ai-enrichment identity from the job's credential | Sections 5.4 and 5.5 |
| `remediate_heapdump_restart` | Catalogued level 2 job: capture a heap dump and restart | Section 2.1 |

Every diagnostic role is read-only and returns evidence items in the format defined in section 5.2 of the implementation design.
