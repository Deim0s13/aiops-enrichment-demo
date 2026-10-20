# AAP content

Playbooks in this directory are run by Ansible Automation Platform as job templates inside the demo. Phase 07 declares the job templates, workflow and credentials that point at them. This repository is the AAP project they are synced from.

| Directory | Contents | Runs as |
|---|---|---|
| `integration/` | Stand-in for the monitoring-to-ITSM integration: creates the incident from an Alertmanager alert (flow step 1) | Its own rulebook activation and ServiceNow identity, separate from the AI path |
| `diagnostics/` | One playbook per diagnostic, each read-only and bounded (flow step 3) | `aiops-diagnostics` service account |
| `enrichment/` | Workflow steps: set state to pending, call the enrichment service, write the work note, failure branch (flow steps 4 and 5) | `svc-ai-enrichment` ServiceNow identity for writes |
| `demo/` | Presenter tools, not part of the incident flow: `trigger_fault.yml` starts the `payments-notify` memory fault, single or recurring (job template Demo &#124; Trigger memory fault) | The AAP automation host, from the `aap` namespace |
| `remediation/` | Catalogued jobs an engineer can launch from a work note (level 2) | The engineer's own AAP account |

Playbooks here stay thin and call roles from the `demo.aiops` collection.
