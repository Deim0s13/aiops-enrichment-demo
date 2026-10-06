# AI-assisted incident enrichment: demo kit

A reproducible demonstration of AI-assisted incident enrichment using Red Hat Ansible Automation Platform (AAP) and Red Hat OpenShift AI. When a fault raises an incident in ServiceNow, Event-Driven Ansible launches an AAP workflow that gathers read-only diagnostics, retrieves approved runbooks, asks a self-hosted model for cited guidance, and writes an AI-labelled work note back to the incident. Where a catalogued fix exists, the work note recommends the AAP job an engineer can launch.

The whole environment is built and configured with Ansible playbooks, so it can be rebuilt from an empty cluster whenever a demo environment expires.

> **Status:** early scaffold. The repository structure, secrets model and design are in place. The build phases are stubs and nothing is deployable yet.

## What the demo shows

| Scenario | What the audience sees |
|---|---|
| Value | A real memory fault raises an incident, and a cited work note with a recommended job appears within a minute |
| Trust | A fault with no runbook produces "insufficient evidence" rather than invented advice |
| Failure handling | Revoking the model gateway key leaves incident handling untouched, with "enrichment unavailable" recorded on the incident |
| Scaling | A second incident family is added with new Ansible content and runbooks only |
| Traceability | Any work note can be followed to its model trace, prompt version and sources |

All data is fictional: a fictional organisation, fictional services and a synthetic knowledge corpus.

## Documentation

- [Implementation design](docs/implementation-design.md): how the demo implements the reference architecture, what it simplifies, and the acceptance criteria
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

These steps describe the intended workflow. The phases are not implemented yet.

```bash
# One-off setup
pre-commit install
ansible-navigator run playbooks/00_secrets.yml --ee false   # starts Vault on your laptop
# Load your secrets into Vault at the paths listed in SECURITY.md

# For each new demo environment
ansible-builder build -f execution-environment/execution-environment.yml -t localhost/aiops-demo-ee:latest
ansible-navigator run site.yml                     # full build
ansible-navigator run site.yml --tags platform     # or one phase at a time
ansible-navigator run verify.yml                   # check the acceptance criteria

# Between demo runs
ansible-navigator run reset.yml
```

`00_secrets.yml` runs outside the execution environment (`--ee false`) because it manages a container on your laptop. Everything else runs inside it.

## Licence

Apache License 2.0. See [LICENSE](LICENSE).

This is an independent demonstration kit. It is not a Red Hat product and is not supported by Red Hat.
