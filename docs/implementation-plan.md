# AI-assisted incident enrichment: demo implementation plan

| | |
|---|---|
| **Version** | 0.1 draft |
| **Date** | October 2026 |
| **Implements** | [Implementation design](implementation-design.md) v0.1 |
| **Status** | Draft for review |

## 1 Approach

The demonstration is delivered in seven milestones. Each one ends with something that runs end to end and can be shown, so progress is visible from the second milestone onwards and a problem in one area is found before the next is built on it.

Milestones and build phases are different things. A build phase (`playbooks/00` to `08`) is a step in deployment order, and it is what `site.yml` runs. A milestone is a delivery increment, and most milestones add to several phases at once. Milestone 2, for example, adds a first version of phases 04, 07 and 08 together, so that an incident gets a work note before any of those phases is complete. Section 3 maps one to the other.

Three rules apply to every milestone:

1. **Rebuild before moving on.** A milestone is complete only when it works on a fresh environment through `site.yml`, not just on the environment it was developed on.
2. **Record what was learned.** Each milestone updates the implementation design where reality differs from it, and closes or raises open items.
3. **Pin what works.** Collection, image and model versions are pinned once the phase that uses them has built successfully.

### Working model

The playbooks are written in this repository and run from the operator's laptop against the demo environment. Code can be drafted and linted without an environment, but anything that touches the cluster, AAP or ServiceNow is proven only by a run. Milestones 0 and 1 are therefore planned so that drafting happens before an environment is requested, and environment time is spent running and fixing rather than writing.

## 2 Milestones

### M0 Readiness

**Goal:** every decision and entitlement needed for the first build is in place before an environment is requested.

| ID | Task | Closes |
|---|---|---|
| M0.1 | Obtain an AAP subscription manifest that can be used in demo environments | OI06 |
| M0.2 | Request a ServiceNow PDI, choose a release, and load demo data | |
| M0.3 | Generate an Automation Hub token and log in to registry.redhat.io on the laptop | |
| M0.4 | Install Podman, `ansible-navigator`, `ansible-builder` and `pre-commit` on the laptop | |
| M0.5 | Implement `00_secrets.yml`: Vault container, KV engine, read-only policy and AppRole. Load the personal secrets by hand | |
| M0.6 | Implement `00_preflight.yml` and the `secrets` role, with both the Vault and local backends | |
| M0.7 | Confirm the execution environment base image for AAP 2.7, then build the execution environment and pin the collection versions that resolve | |
| M0.8 | ~~Name the fictional organisation and its services~~ Done: ACME Bank | OI07 |
| M0.9 | ~~Confirm publication approval~~ Done: private in the author's GitHub under Apache 2.0, shared with colleagues as collaborators; going public is a later decision | OI09 |
| M0.10 | ~~Ask the ops team whether their incident family can be reproduced~~ Done: keep DD01; design a second family in M5 | OI08 |

**Exit criteria:** preflight passes on the laptop against Vault, with no environment yet. The execution environment builds.

**Status: complete (2026-10-13).** Preflight passes on the operator's laptop against Vault, inside the execution environment, with live checks of the registry, Automation Hub and ServiceNow credentials.

Lessons from the first real run, now reflected in the code and the setup guide:

- `ansible-builder` prints the full `podman build` command, so a build argument passed as `NAME=value` exposes its value. The Automation Hub token is now passed by name only, and Podman reads it from the environment. The exposed token was revoked.
- The AAP 2.7 execution environment repository publishes no `latest` tag. The base image is pinned to `2.20-1790991048` (ansible-core 2.20).
- ansible-builder must use `/usr/bin/python3.12` explicitly, because system packages installed during the build can redirect `/usr/bin/python3` to a Python without `pip`.
- `ansible.eda` requests `systemd-python`, which cannot compile in the minimal image and is not needed. It is excluded.
- Setting `collections_path` in `ansible.cfg` replaces the default search path, so it must include the execution environment's `/usr/share/ansible/collections`.
- Collection versions are pinned to those the first build resolved.

**Estimate:** 1 day, mostly waiting on entitlements.

### M1 Platform and model serving

**Goal:** a fresh environment goes from empty to a served model behind the gateway, and the rebuild time is known.

| ID | Task | Closes |
|---|---|---|
| M1.1 | Draft phases 01, 02 and 03 before requesting the environment | |
| M1.2 | ~~Request the g6.16xlarge environment with a root volume of about 500 GB. Record what the environment provides out of the box~~ Done: recorded in section 7.1 of the design. The GPU stack and OpenShift AI 3.5.1 are provided, so phase 01 checks rather than installs (DD13) | |
| M1.3 | Phase 01: free the GPU, check Node Feature Discovery, the GPU Operator and storage, and enable user workload monitoring with its Alertmanager. Done: ran on the first environment (2026-10-14); user workload Prometheus and Alertmanager running, one GPU allocatable | |
| M1.4 | ~~Confirm the gateway capability~~ Done: Models-as-a-Service (DD14). Key issuance confirmed (2026-10-14): the build mints the enrichment service's key with the service account's own token, without the dashboard | OI02 |
| M1.5 | ~~Confirm whether MLflow tracing is provided~~ Done: the `mlflowoperator` component | OI03 |
| M1.6 | Test two or three candidate models for citation adherence, using a hand-built prompt with sample evidence and passages. Phase 02 serves Granite 3.1 8B as the starting point; the test is a separate playbook that serves each candidate's validated FP8 ModelCar in turn and calls it through MaaS with the same evidence and prompt | OI04 |
| M1.7 | Phase 02, in three parts: (1) OpenShift AI version check and Red Hat Connectivity Link, with the reusable operator role; (2) PostgreSQL, the MaaS gateway, and enabling MaaS and MLflow; (3) the model, its subscription, the enrichment service's API key and access checks. Parts 1 and 2 done (2026-10-14): Connectivity Link, PostgreSQL, the MaaS gateway, and MaaS and MLflow enabled. Part 2b, the MLflow server, done the same day. Part 3 done (2026-10-14): Granite served on the L4, the enrichment service's policy, subscription and key, and the access checks passing through the gateway | |
| M1.8 | Phase 03: AAP operator, instance and manifest upload | |
| M1.9 | ~~Confirm whether the cluster's routes are reachable from the internet~~ Done: reachable, with a publicly trusted certificate, so the trigger is a push | OI01 |
| M1.10 | Rebuild from empty and time each phase | |

**Exit criteria:** a request with the enrichment service's gateway key returns a model response, and the same request with no key or a revoked key is refused. AAP is licensed and reachable. Phase timings are recorded in section 7 of the design.

**Estimate:** 2 days.

**Decision point:** if the rebuild takes much longer than 90 minutes, decide whether to accept it, cache more (for example, mirror operator images) or split the build so the slow phases run once per environment.

**Progress and lessons so far (2026-10-14).** Phases 01 and 02 (parts 1, 2 and 2b) run on the first environment. Lessons:

- The environment is the RHDP OpenShift AI catalogue item and already provides the GPU stack and OpenShift AI (design section 7.1), so phase 01 checks rather than installs (DD13).
- The cluster API uses a certificate from the cluster's own CA. The build verifies it against `kube-root-ca.crt`, loaded into Vault with the URL and token, rather than turning verification off.
- `kubernetes.core` 6.6.0 prints the cluster token at `-vvv`, even on success. The `secrets` role refuses to run at that verbosity.
- `kubernetes.core.k8s_exec` fails to import with current Kubernetes Python clients, so in-cluster setup runs as Jobs.
- PostgreSQL clients that have a CA file configured treat `sslmode=require` as `verify-ca`. MLflow's does, so it is given the OpenShift service CA and connects with `verify-full`.
- The single-node API server occasionally drops a connection; the DataScienceCluster patch retries.
- Red Hat image tags for `rhel9/postgresql-16` are build timestamps; the list also contains digest-named signature entries.
- MaaS keeps a model `Pending` ("Awaiting governance pairing") until an active auth policy and subscription both cover it, so the build waits for MaaS to accept the model only after creating them. The simulated MaaS used to test the build accepted models on its own, which hid this; simulations should copy the product's gating, not only its happy path.
- MaaS publishes each model under an ID of the form `publishers/NAMESPACE/models/NAME` and routes the shared `/v1/chat/completions` endpoint on the request's `model` field before checking the key, so a wrong model name gets a 404 even without a key. The build reads the ID and URL from MaaS's model list, as a client would, and stores them with the key.
- A missing MaaS key is refused with 401 and a revoked one with 403; the checks accept either.
- Looping a later task over a Kubernetes task's registered results prints the cluster token at `-vv`, because each item carries the module invocation. Such results are reduced to the fields needed first.

### M2 Thin end to end

**Goal:** an incident raised by hand in ServiceNow receives an AI-labelled work note, written once, with failure handled. The enrichment service returns a fixed response, so this milestone proves the plumbing, not the AI.

| ID | Task | Closes |
|---|---|---|
| M2.1 | Phase 08 (part): custom incident fields, service identities, the business rule or polling configuration, and the "enrichment ready" notification | |
| M2.2 | Rulebook `incident_enrichment.yml`: receive, validate and pass only the defined fields | |
| M2.3 | Phase 04 (part): project, credentials, EDA activation and the enrichment workflow with its failure branch | |
| M2.4 | Role `itsm_worknote`: idempotent, AI-labelled work note and enrichment fields | |
| M2.5 | Phase 07 (part): enrichment service skeleton returning a fixed, schema-valid response, built in-cluster, with network policies | |
| M2.6 | Start `verify.yml` with the idempotency, recursion and concurrent update checks | |
| M2.7 | Start `reset.yml`: close demo incidents and clear enrichment fields | |

**Exit criteria:** a manually raised incident gets exactly one work note within a minute. Rerunning the workflow adds no duplicate. The update does not retrigger the workflow. Stopping the enrichment service produces an "enrichment unavailable" note, and the incident stays with its team.

**Estimate:** 2 days.

### M3 Real fault and evidence

**Goal:** a fault triggered on demand raises the incident through the integration stand-in, and the workflow gathers real evidence.

| ID | Task | Closes |
|---|---|---|
| M3.1 | Sample service `payments-notify` with a heap growth endpoint, sized to fail predictably | |
| M3.2 | Phase 05: deployment, alert rules for heap usage and restarts, and Alertmanager routing | |
| M3.3 | Integration stand-in: rulebook `integration_alerts.yml`, its playbook in `automation/integration/` and its own ServiceNow identity | |
| M3.4 | Roles `evidence`, `diag_pod_status`, `diag_metrics`, `diag_changes` and `diag_logs`, with runtime and output limits | |
| M3.5 | Phase 04 (part): diagnostic job templates in the workflow, run as the read-only `aiops-diagnostics` service account | |
| M3.6 | Extend `reset.yml` to restart the sample service and clear heap dumps | |

**Exit criteria:** triggering the fault raises an incident within two minutes, and the workflow passes evidence in the common format to the enrichment service. A diagnostic that times out or returns too much output is handled without failing the workflow.

**Estimate:** 2 days.

### M4 Knowledge and real enrichment

**Goal:** the work note contains real, cited guidance, and the demo shows both the value and the trust scenario.

| ID | Task | Closes |
|---|---|---|
| M4.1 | Write the corpus: current runbooks and resolutions, near-miss runbooks, a superseded runbook, a restricted document, and a deliberate gap | |
| M4.2 | Confirm pgvector is available in the chosen PostgreSQL image | OI05 |
| M4.3 | Phase 06: knowledge index and ingestion job, storing labels with each passage | |
| M4.4 | Enrichment service: sanitisation, filtered retrieval, the prompt, the gateway call, schema and citation validation, the insufficient-evidence path and provenance | |
| M4.5 | Tracing of every model call, with the trace ID written into the work note | |
| M4.6 | Extend `verify.yml` with the wrong-version, access filtering, prompt injection, sensitive data, and latency and cost checks | |
| M4.7 | Tune the prompt and relevance threshold against the scenarios, and version the prompt | |

**Exit criteria:** scenarios S1 (level 1 only), S2, S3 and S5 pass, and every automated check in section 9 of the design passes.

**Estimate:** 4 days. The corpus is the largest single task.

**Decision point:** if the selected model fails the prompt injection or citation checks after tuning, try the next candidate from M1.6 before changing the design.

### M5 Level 2 and a second incident family

**Goal:** the work note recommends a catalogued job that an engineer can launch, and a second incident family is added as a content-only change.

| ID | Task | Closes |
|---|---|---|
| M5.1 | Role `remediate_heapdump_restart` and its job template, launchable only by the engineer's account | |
| M5.2 | Level 2 catalogue passed with the enrichment request, and a launch link in the work note | |
| M5.3 | Second incident family: one new diagnostic, its runbooks and a way to trigger it | |

**Exit criteria:** scenario S1 passes in full, including recovery after the engineer launches the job. Scenario S4 passes with no change to the enrichment service.

**Estimate:** 1 day.

### M6 Demo readiness

**Goal:** the demo can be run by someone other than its author, and survives a bad day.

| ID | Task | Closes |
|---|---|---|
| M6.1 | Complete `reset.yml` and `verify.yml`, and run both on a fresh build | |
| M6.2 | Time a manual diagnosis of the S1 incident by an engineer, for the side-by-side comparison | |
| M6.3 | Write the run sheet: setup, the five scenarios, talking points, and recovery steps if something fails | |
| M6.4 | Record a fallback video of the full run | |
| M6.5 | Prepare the leadership calculation: evidence-gathering minutes per incident, multiplied by monthly incident volume, with the baseline left for the customer to fill in | |
| M6.6 | Have a colleague build and run the demo from the README alone | |
| M6.7 | Final secret and content review, so the repository is ready to make public if and when that is decided | |

**Exit criteria:** a colleague completes a build and a full run without help.

**Estimate:** 1.5 days.

## 3 Milestones and build phases

| Phase | M0 | M1 | M2 | M3 | M4 | M5 | M6 |
|---|---|---|---|---|---|---|---|
| 00 Secrets and preflight | Build | | | | | | |
| 01 Platform | | Build | | | | | |
| 02 OpenShift AI | | Build | | | | | |
| 03 AAP | | Build | | | | | |
| 04 AAP content | | | Start | Extend | | Extend | |
| 05 Workload | | | | Build | | Extend | |
| 06 Knowledge | | | | | Build | Extend | |
| 07 Enrichment service | | | Skeleton | | Build | Extend | |
| 08 ServiceNow | | | Build | Extend | | | |
| `reset.yml` and `verify.yml` | | | Start | Extend | Extend | | Complete |

## 4 Timeline and environments

The estimates add up to about 13.5 working days, or two and a half to three weeks allowing for waiting and rework. The critical path runs through M1, because the gateway, tracing and model questions (OI02, OI03, OI04) decide how phase 02 and the enrichment service are written.

Demo environments expire after a fixed number of days, so the plan assumes at least two environments:

| Environment | Used for | Notes |
|---|---|---|
| First | M1 to M3 | Request once M0 is complete and phases 01 to 03 are drafted |
| Second | M4 to M6 | Start with a full rebuild, which doubles as the rebuild test |

If an environment expires mid-milestone, nothing is lost except in-cluster state, because everything else is in the repository. The rebuild time measured in M1 is what makes this acceptable.

## 5 Things only the operator can do

These need personal accounts or the environment, so they cannot be prepared in advance:

- Obtain the AAP manifest, Automation Hub token, pull secret and PDI (M0.1 to M0.3)
- Request each demo environment and load its API token into Vault (M1.2)
- Run every build and share the output when something fails
- Check what the environment provides out of the box (M1.2) and answer OI01 to OI03 from it
- Agree publication approval (M0.9) and arrange the colleague test (M6.6)

## 6 Risks

| Risk | Effect | Response |
|---|---|---|
| Models-as-a-Service cannot be built reliably on the single node, or keys cannot be issued by a playbook | The kill switch and attribution story weakens | Fall back to a service account token on the `LLMInferenceService`, and record it as a deviation from ADR06 |
| A small model does not keep to citations or resists prompt injection poorly | The trust scenario fails | Test early (M1.6), keep two candidates, and rely on service-side validation rather than the model |
| The cluster is not reachable from ServiceNow | Push trigger cannot work | Polling fallback (DD03), decided in M1.9 |
| Rebuild time is too long for the environment lifetime | Less time for building and rehearsal | Measure in M1.10 and act at the decision point |
| AAP 2.7 collection or execution environment names differ from what the scaffold assumes | Early build failures | Resolve in M0.7 before any environment time is spent |
| The corpus reads as too convenient to architects | The demo looks staged | Include near-misses and a gap, and say openly that real results depend on runbook quality |
