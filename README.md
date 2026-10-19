# AI-assisted incident enrichment: demo kit

A reproducible demonstration of AI-assisted incident enrichment using Red Hat Ansible Automation Platform (AAP) and Red Hat OpenShift AI. When a fault raises an incident in ServiceNow, Event-Driven Ansible launches an AAP workflow that gathers read-only diagnostics, retrieves approved runbooks, asks a self-hosted model for cited guidance, and writes an AI-labelled work note back to the incident. Where a catalogued fix exists, the work note recommends the AAP job an engineer can launch.

The whole environment is built and configured with Ansible playbooks, so it can be rebuilt from an empty cluster whenever a demo environment expires.

> **Status:** milestone M2 (thin end to end) complete: an incident raised in ServiceNow gets an AI-labelled work note from the enrichment service through EDA and AAP, with nobody touching AAP, and `verify.yml` checks it. Build phases 01 to 04, 06 (the enrichment service, a skeleton until M3) and 07 (AAP content and the trigger) are implemented; 05 (knowledge) and 08 (workload) come in M3 and M4.

## What the demo shows

| Scenario | What the audience sees |
|---|---|
| Value | A real memory fault raises an incident, and a cited work note with a recommended job appears within a minute |
| Trust | A fault with no runbook produces "insufficient evidence" rather than invented advice |
| Failure handling | Revoking the model gateway key leaves incident handling untouched, with "enrichment unavailable" recorded on the incident |
| Scaling | A second incident family is added with new Ansible content and runbooks only |
| Traceability | Any work note can be followed to its model trace, prompt version and sources |

All data is fictional: a fictional organisation, ACME Bank, with fictional services and a synthetic knowledge corpus.

## Documentation

- [Implementation design](docs/implementation-design.md): how the demo implements the reference architecture, what it simplifies, and the acceptance criteria
- [Implementation plan](docs/implementation-plan.md): milestones, tasks and exit criteria
- [Laptop setup](docs/laptop-setup.md): tools, Vault, secrets and preflight
- [Build guide](docs/build-guide.md): building the demo on each new demo environment
- [Security and secrets](SECURITY.md): how secrets are handled and the rules for contributors
- [Contributing](CONTRIBUTING.md)

## Repository layout

```text
aiops-enrichment-demo/
├── site.yml, reset.yml, verify.yml   build, reset between runs, check acceptance criteria
├── ansible.cfg, ansible-navigator.yml
├── secrets.example.yml               template for the secrets you bring; never filled in here
├── inventory/                        environment settings (no secrets)
├── playbooks/                        build phases, run from your laptop
├── roles/                            roles used by the build phases
├── evaluation/                       the model selection test (docs/model-selection.md), run from your laptop
├── automation/                       playbooks AAP runs as job templates
│   ├── integration/                  stand-in for the monitoring-to-ITSM integration
│   ├── diagnostics/                  read-only evidence gathering
│   ├── enrichment/                   workflow steps: call the enrichment service, write the work note
│   └── remediation/                  catalogued jobs an engineer can launch (level 2)
├── rulebooks/                        Event-Driven Ansible rulebooks
├── collections/
│   ├── requirements.yml              collections used by the build and by AAP
│   └── ansible_collections/demo/aiops/   reusable roles for diagnostics, ITSM write-back and remediation
├── execution-environment/            execution environment definition
├── services/
│   ├── enrichment/                   enrichment service source, built in-cluster
│   └── payments-notify/              sample service with a reproducible fault
├── knowledge/                        synthetic runbooks and prior resolutions, with approval metadata
└── docs/
```

There are two kinds of playbook in this repository, separated by who runs them. `playbooks/` builds the environment and runs from your laptop through `ansible-navigator`. `automation/` and `rulebooks/` are the content AAP runs inside the demo, and this repository is the AAP project they are synced from.

## Prerequisites

**On your laptop**

- Podman
- `ansible-navigator`, `ansible-builder` and `pre-commit`
- HashiCorp Vault Community Edition, run as a container by `playbooks/00_secrets.yml`

**Accounts and entitlements, each your own**

- A Red Hat account with an OpenShift pull secret, an AAP subscription manifest, and Automation Hub access for certified collections
- A ServiceNow Personal Developer Instance (PDI)

**Demo environment**

- Single-node OpenShift with OpenShift AI 3.5 on an AWS g6.16xlarge (64 vCPU, 256 GiB, one NVIDIA L4), with a root volume of about 500 GB

## Getting started

Start with [docs/laptop-setup.md](docs/laptop-setup.md), which takes you from a bare laptop to a passing preflight check before any demo environment exists. In outline:

```bash
# One-off setup on the laptop
ansible-galaxy collection install -r collections/requirements-laptop.yml
ansible-playbook playbooks/00_secrets.yml          # starts and configures Vault on your laptop
# Load your secrets into Vault (see the guide), then build the execution environment
source ~/.config/aiops-demo/approle.env
ansible-navigator run playbooks/00_preflight.yml -e preflight_include_cluster=false

# For each new demo environment: see docs/build-guide.md (phases 01 to 04, 06 and 07 are implemented; 05 and 08 are not yet)
ansible-navigator run site.yml                     # full build
ansible-navigator run site.yml --tags platform     # or one phase at a time
ansible-navigator run verify.yml                   # check the acceptance criteria

# Between demo runs
ansible-navigator run reset.yml
```

`00_secrets.yml` runs with `ansible-playbook` directly rather than inside the execution environment, because it manages a container on your laptop. Everything else runs inside it.

## Licence

Apache License 2.0. See [LICENSE](LICENSE).

This is an independent demonstration kit. It is not a Red Hat product and is not supported by Red Hat.
