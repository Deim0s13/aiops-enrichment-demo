# AAP content

Playbooks in this directory are run by Ansible Automation Platform as job templates inside the demo. Phase 07 declares the job templates, workflow and credentials that point at them. This repository is the AAP project they are synced from.

| Directory | Contents | Runs as |
|---|---|---|
| `integration/` | Stand-in for the monitoring-to-ITSM integration (flow step 1, DD19): `raise_incident.yml` raises or updates one incident per service and problem from an Alertmanager notification | Its own rulebook activation, AAP user (`svc-eda-integration`) and ServiceNow identity (`svc-monitoring`), separate from the AI path |
| `diagnostics/` | One playbook per diagnostic (pod status, metrics, recent changes, log excerpt), each read-only and bounded (flow step 3); they run in parallel and publish their evidence for the work note step | `aiops-diagnostics` service account, through a time-limited token in an AAP credential (DD20) |
| `enrichment/` | Workflow steps: set state to pending, call the enrichment service, write the work note, failure branch (flow steps 4 and 5) | `svc-ai-enrichment` ServiceNow identity for writes |
| `demo/` | Presenter tools, not part of the incident flow: `trigger_fault.yml` starts the `payments-notify` memory fault, single or recurring (job template Demo &#124; Trigger memory fault) | The AAP automation host, from the `aap` namespace |
| `knowledge/` | The knowledge loop (scenario S6): `draft_resolution.yml` drafts a resolution from an engineer's resolution notes and opens a pull request (DD33); `refresh_index.yml` reloads the index after a push to `main` changes the corpus (DD34) | The knowledge bot's GitHub App, with `svc-ai-enrichment` to read the incident; the refresh as the `aiops-knowledge-refresh` service account, which can only run the ingestion Job |
| `remediation/` | Catalogued jobs an engineer can launch from a work note (level 2) | The engineer's own AAP account |

Playbooks here stay thin and call roles from the `demo.aiops` collection.
