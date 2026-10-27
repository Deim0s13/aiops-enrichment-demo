# AI-assisted incident enrichment: demo implementation plan

| | |
|---|---|
| **Version** | 0.1 draft |
| **Date** | October 2026 |
| **Implements** | [Implementation design](implementation-design.md) v0.1 |
| **Status** | Draft for review |

## 1 Approach

The demonstration is delivered in seven milestones. Each one ends with something that runs end to end and can be shown, so progress is visible from the second milestone onwards and a problem in one area is found before the next is built on it.

Milestones and build phases are different things. A build phase (`playbooks/00` to `08`) is a step in deployment order, and it is what `site.yml` runs. A milestone is a delivery increment, and most milestones add to several phases at once. Milestone 2, for example, adds a first version of phases 04, 06 and 07 together, so that an incident gets a work note before any of those phases is complete. Section 3 maps one to the other.

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
| M0.1 | ~~Obtain an AAP subscription manifest that can be used in demo environments~~ Done | OI06 |
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
| M1.6 | ~~Test two or three candidate models for citation adherence~~ Done (2026-10-15): Granite 3.1 8B, Llama 3.1 8B and Qwen3 8B tested through MaaS ([model-selection.md](model-selection.md)); Qwen3 8B chosen for engineer-reviewed enrichment and served by phase 02 | OI04 |
| M1.7 | Phase 02, in three parts: (1) OpenShift AI version check and Red Hat Connectivity Link, with the reusable operator role; (2) PostgreSQL, the MaaS gateway, and enabling MaaS and MLflow; (3) the model, its subscription, the enrichment service's API key and access checks. Parts 1 and 2 done (2026-10-14): Connectivity Link, PostgreSQL, the MaaS gateway, and MaaS and MLflow enabled. Part 2b, the MLflow server, done the same day. Part 3 done (2026-10-14): Granite served on the L4, the enrichment service's policy, subscription and key, and the access checks passing through the gateway. Then split into roles by owning team (DD15), with retries on reads | |
| M1.8 | Phase 03: AAP operator, instance and manifest upload. Operator and platform done (2026-10-15): AAP 2.7 with Controller and Event-Driven Ansible on the shared node. Manifest upload built 2026-10-16, applied from Vault by phase 03 | OI06 |
| M1.9 | ~~Confirm whether the cluster's routes are reachable from the internet~~ Done: reachable, with a publicly trusted certificate, so the trigger is a push | OI01 |
| M1.10 | Rebuild from empty and time each phase. First rebuild done (2026-10-16) on a second environment, following the build guide; phases 02 and 03 took roughly 20 minutes together, not timed precisely. It found one environment difference (a standalone Authorino), now handled. Time each phase with `time` on the next rebuild | |

**Exit criteria:** a request with the enrichment service's gateway key returns a model response, and the same request with no key or a revoked key is refused. AAP is licensed and reachable. Phase timings are recorded in section 7 of the design.

**Estimate:** 2 days.

**Decision point:** if the rebuild takes much longer than 90 minutes, decide whether to accept it, cache more (for example, mirror operator images) or split the build so the slow phases run once per environment.

**Progress and lessons so far (2026-10-15).** Phases 01, 02 and 03 (without the manifest) run on the first environment, and the model is chosen. Lessons:

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
- The cluster session token expires daily, and an expired token used to surface as a traceback from whichever task first called the cluster. The `secrets` role now checks the token whenever a phase reads the cluster group, and stops with a clear message before anything changes.
- The model selection test: constrained output works through MaaS (all 45 constrained answers valid, with only supplied IDs). Llama 3.1 8B once added a database failover step because a planted log line asked it to, and Granite 3.1 8B declined cases its runbook covered. Qwen3 8B was the only candidate both safe and useful, but cautious: prompt work in M3 targets its declined C4 and missing job on C3. Two gates first measured more than safety; they were corrected, recorded and applied to the saved answers.
- RHDP environments differ between orders: the second shipped the Authorino operator on its own, at a version Connectivity Link would not install alongside. Phase 02 now removes it first. Rebuilding on fresh environments is how such differences are found.
- AAP 2.7 fits beside OpenShift AI and the model on one g6.16xlarge: before AAP, about a quarter of the node's CPU and a fifth of its memory were requested.
- The single-node API server dropped connections three times in two days, part way through a response. Waits already retried; single-shot reads now retry too. Writes do not, so a failed change stops the build.
- Looping a later task over a Kubernetes task's registered results prints the cluster token at `-vv`, because each item carries the module invocation. Such results are reduced to the fields needed first.
- ServiceNow (M2.1, 2026-10-16 to 19): the PDI refuses access rule (ACL) changes over the API, even from the administrator, so the identities' limits are guard business rules. The first guards looked right but enforced nothing: they called a role check that exists only in the browser, the script failed, and ServiceNow let each write through. The build check, acting as each identity, caught it on the first run. Controls are proved by trying to break them, not by reading their configuration.
- The GitHub token for AAP (DD16): GitHub's repository details report what the token's owner may do, not the token, so preflight proves read-only access by trying a harmless write and expecting it to be refused, the same approach as the ServiceNow checks.
- Phase 07's first run (2026-10-19): every job failed with `Exec format error`, because the execution environment built on an Apple silicon laptop is arm64 and the cluster node is x86_64. The laptop now builds a second, linux/amd64 image for the cluster, and the publish step checks the architecture before pushing. Phase 07's checks caught it on test incidents, before any real incident depended on it.
- AAP 2.7 details found by phase 07: the operator sets up no decision environment, so the kit pins Red Hat's supported one; and Ansible does not template the keys of a literal mapping, so a header named by a variable must be built as an expression.
- The rulebook can hand a field over as a number (priority 3), which the enrichment service's contract rejected (HTTP 422). The failure branch caught it and marked the incident unavailable, as designed; the note step now sends every field as text, and the service's contract stays strict.
- The second clean build from empty (2026-10-19) needed no fixes, up to and including phase 04. The next build is timed phase by phase (M1.10).
- The third clean build from empty (2026-10-20) ran every implemented phase in the new order, 01 to 04, 06 and 07, with no code changes. The only interruption was a few minutes in which the cluster's API was unavailable (connection refused, then OpenShift's own resource types missing); rerunning the two affected steps, which are idempotent, completed the build. On a single node, the control plane restarting is a normal event to rerun through, not a fault in the kit.

### M2 Thin end to end

**Goal:** an incident raised by hand in ServiceNow receives an AI-labelled work note, written once, with failure handled. The enrichment service returns a fixed response, so this milestone proves the plumbing, not the AI.

| ID | Task | Closes |
|---|---|---|
| M2.1 | Phase 04 (part): custom incident fields, assignment group, custom roles, service identities narrowed by guard business rules, and the "enrichment ready" notification. Phases renumbered so ServiceNow comes before AAP content, which needs the identities and writes the EDA event stream address back. Fields, group, roles and identities done (2026-10-16). The PDI refuses ACL changes over the API, so the identities hold `itil` narrowed by guard business rules (design section 6.1), proved on every build by checks that act as each identity. Guards, checks, notification and a fictional on-call engineer done (2026-10-19); all five checks pass. The business rule moves to M2.3, with the event stream it calls | |
| M2.1a | Execution environment pushed to the cluster's internal registry by a laptop-side playbook, and a read-only GitHub token in Vault for AAP's project (DD16, DD17). Decided 2026-10-19; token stored and checked by preflight; `07_execution_environment.yml` written | |
| M2.2 | Rulebook `incident_enrichment.yml`: receive, validate and pass only the defined fields. Written (2026-10-19) | |
| M2.3 | Phase 07 (part): project, credentials, EDA activation and the enrichment workflow with its failure branch. Built and proved with a hand-crafted event first; the ServiceNow business rule that pushes to the event stream, and the write-back of its address and token, come last, so each link is tested alone before they are joined. Phase 07 done (2026-10-20): all five checks pass, from a real event through the event stream to the work note, the failure branch, a retry that adds nothing and the trigger user's limits. The business rule and the REST Message that carries the event stream's address and token done (2026-10-20): an incident raised as svc-monitoring is enriched with no other action, its "AI enrichment ready" email is queued, and an incident outside the rule is left alone | |
| M2.4 | Role `itsm_worknote`: idempotent, AI-labelled work note and enrichment fields. Written (2026-10-19), with a placeholder note until M2.5 | |
| M2.5 | Phase 06 (part): enrichment service skeleton returning a fixed, schema-valid response, built in-cluster, with network policies. Done (2026-10-20): TLS from the service CA, its own API token, checks from inside the cluster; the workflow's note step asks it and validates its answer, and every phase 07 check passes through it, hands-off included. Phases renumbered by dependency: 05 knowledge, 06 enrichment service, 07 AAP content and the trigger, 08 workload | |
| M2.6 | Start `verify.yml` with the idempotency, recursion and concurrent update checks. Written (2026-10-20): V1 time to note, V2 no retrigger, V3 retry, V4 concurrent update, V5 service stopped. All five pass (2026-10-20); the first note arrived 17 seconds after the incident opened | |
| M2.7 | Start `reset.yml`: close demo incidents and clear enrichment fields. Done (2026-10-20): resolves and closes the demo's own incidents with a close note, rather than clearing their fields, so their history stays; deletes build-check leftovers | |

**Exit criteria:** a manually raised incident gets exactly one work note within a minute. Rerunning the workflow adds no duplicate. The update does not retrigger the workflow. Stopping the enrichment service produces an "enrichment unavailable" note, and the incident stays with its team.

**Status: complete (2026-10-20).** Every exit criterion is met and checked by `verify.yml`, with incidents raised as `svc-monitoring` rather than by hand: one note, 17 seconds after the incident opened; no duplicate on a retry; no retrigger from the enrichment's own update; an engineer's concurrent edit kept; and an "AI enrichment unavailable" note, with the incident left with its team, when the enrichment service is stopped.

**Estimate:** 2 days.

### M3 Real fault and evidence

**Goal:** a fault triggered on demand raises the incident through the integration stand-in, and the workflow gathers real evidence.

**Status: complete (2026-10-22).** Triggering the fault raises one incident through the integration stand-in, at priority 2, about a minute after the OOM kill and its critical alert, and the workflow passes evidence from four diagnostics in the design 5.2 format to the enrichment service, which phase 08 checks on every run. A diagnostic that fails or times out leaves a gap item and the note is still written, and phase 07 proves that on incidents with no configuration item. `verify.yml` V1 to V5 pass with the diagnostics in the path: the note arrives 20 seconds after the incident opens, for an incident with no configuration item, whose diagnostics return quickly. The time for an incident with full diagnostics is measured in M4 (M4.6).

| ID | Task | Closes |
|---|---|---|
| M3.1 | Sample service `payments-notify` with a heap growth endpoint, sized to fail predictably. Done (2026-10-21): single and recurring scenarios, heap equal to the container limit (DD18), and a Demo | Trigger memory fault job template | |
| M3.2 | Phase 08: deployment, alert rules for heap usage and restarts, and Alertmanager routing. Deployment, metrics, alert rules and the fault check done (2026-10-21, stage A: OOMKilled at a heap peak of 83.5%, both alerts fired, clean recovery). Routing to the integration stand-in done (2026-10-21, stage B): an AlertmanagerConfig grouped by service and incident family, to an event stream with Basic authentication | |
| M3.3 | Integration stand-in: rulebook `integration_alerts.yml`, its playbook in `automation/integration/` and its own ServiceNow identity. Stage B: one incident per problem with alerts rolled up as work notes, escalation to priority 2 on a critical alert, cleared alerts noted and the incident left open (DD19); its own AAP user. Done (2026-10-21): checked in phase 07 and, from the real fault, in phase 08 (one incident raised by svc-monitoring, two occurrences, priority 2, enriched) | |
| M3.4 | Roles `evidence`, `diag_pod_status`, `diag_metrics`, `diag_changes` and `diag_logs`, with runtime and output limits. Written (2026-10-21, stage C): evidence in the design 5.2 format, a gap item instead of a failure, targets only from the service map keyed by the configuration item; tested against a mock of the cluster and metrics APIs. Done (2026-10-21): from the real fault, the note carries evidence from all four diagnostics | |
| M3.5 | Phase 07 (part): diagnostic job templates in the workflow, run as the read-only `aiops-diagnostics` service account. Written (2026-10-21, stage C): four templates in parallel as the read-only service account, through a 7-day token in an AAP credential (DD20; AAP refuses service account tokens in container group pods); the note step waits for all four; configuration items in phase 04; the skeleton service lists the evidence it receives; checked in phase 08. Done (2026-10-21): INC0010083 raised by the OOM kill at priority 2 and enriched with EV-POD, EV-MET, EV-CHG and EV-LOG evidence | |
| M3.6 | Extend `reset.yml` to restart the sample service. Done (2026-10-22, stage D): a new pod clears the recurring fault; the reset waits until it is ready, then closes the incidents, and an OOMKilled alert still firing afterwards raised no new incident. Clearing heap dumps moved to M5.1, with the job that creates them | |
| M3.7 | Trigger resilience: the ServiceNow trigger retries a post that may pass (no answer, HTTP 429 or 5xx) twice, after 2 and 5 seconds, with the same event ID. Written (2026-10-22) after `verify.yml` V1 caught a single HTTP 500 from the event stream, which lost that incident's trigger. A reconciliation sweep for longer outages is open item OI10, for M6. Done (2026-10-22): installed, and `verify.yml` V1 to V5 pass | |

**Lessons so far (2026-10-21).** Basic authentication reaches an EDA event stream through the platform gateway, so Alertmanager needs no in-cluster listener. Alert timing has to fit the fault: the heap is above half its maximum for only about 90 seconds before the kill, and user workload rules are evaluated every 30 seconds behind the scrape, so a 30-second hold at 60% let the kill come first. The heap alert now fires at 50% with no hold, and the OOMKilled alert keeps the 5-minute window, because 2 minutes was too short for kube-state-metrics' scrape interval. AAP refuses a service account token in a container group's pod spec, automounted or projected, by design: job pods carry no cluster identity of their own, so the diagnostics use a time-limited token in an AAP credential (DD20). Raising the incident on the heap warning ran the diagnostics before the OOM kill, so only critical alerts raise incidents now (DD19). AAP turns empty text into null when it passes workflow artefacts between steps, so the work note step restores the evidence contract's shape before calling the service; and the failure branch now records why a step failed, which found that in one run.

**Exit criteria:** triggering the fault raises an incident within two minutes, and the workflow passes evidence in the common format to the enrichment service. A diagnostic that times out or returns too much output is handled without failing the workflow.

**Estimate:** 2 days.

### M4 Knowledge and real enrichment

**Goal:** the work note contains real, cited guidance, and the demo shows both the value and the trust scenario.

| ID | Task | Closes |
|---|---|---|
| M4.1 | Write the corpus: current runbooks and resolutions, near-miss runbooks, a superseded runbook, a restricted document, and a deliberate gap. Done (2026-10-22): eight documents in `knowledge/`, reviewed; the gap is the MessageHub throttling fault (S2) | |
| M4.2 | Confirm pgvector is available in the chosen PostgreSQL image. Done (2026-10-27): pgvector 0.6.2 | OI05 |
| M4.3 | Phase 05: knowledge index and ingestion job, storing labels with each passage. Written (2026-10-27, DD21): its own database and two identities, row-level security for the reader, the corpus from `main`, BGE small embeddings baked into the image; tested locally against PostgreSQL 16 with pgvector 0.6.2. Done (2026-10-27): phase 05 passes on the cluster, including the search check with the real embedding model | |
| M4.4 | Enrichment service: sanitisation, filtered retrieval, the prompt, the gateway call, schema and citation validation, the insufficient-evidence path and provenance. Written (2026-10-27, DD22): service 0.3.0 with prompt `enrichment-v1` and policy `policy-v1`; the workload's version label, read by the changes diagnostic; the catalogue passed from the inventory; phase 06 checks the whole path with a test card number, phase 08 checks the note is grounded, and phase 05 reports a calibration score for the threshold. Tested locally against PostgreSQL with pgvector and a stand-in gateway. Done (2026-10-27): phases 05 to 08 pass on the cluster; on a real OOM kill the note is `enriched`, grounded in KB-RB-014, KB-RS-044 and KB-RS-031, and nothing superseded, restricted or for another service reaches the model. Retrieval favours short overview sections over the runbook's Diagnosis and Actions, which M4.7 addresses | |
| M4.5 | Tracing of every model call, with the trace ID written into the work note. Written (2026-10-27, DD23): service 0.4.0 traces each request in OpenShift AI's MLflow 3.14, a span per step, tagged with the incident, versions and AAP workflow job; sanitised before tracing, best effort, recorded only once read back; signed in with a one-hour projected token and a role of its own in its own namespace (experiments only, no delete); MLflow telemetry off. Phase 06 reads the trace back from MLflow and searches it for the test card number. Tested locally against MLflow 3.14, including MLflow down, stopping mid-life and hanging. Done (2026-10-27): on the cluster the service writes with a role of its own (OpenShift AI 3.5 names its integration role `mlflow-operator-mlflow-integration`, and it is broader than tracing needs); phase 06 reads the trace back from MLflow; the memory fault's note carries `trace tr-… (MLflow)`, tagged with workflow job and event | |
| M4.6 | Extend `verify.yml` with the wrong-version, access filtering, prompt injection, sensitive data, and latency and cost checks | |
| M4.7 | Tune the prompt and relevance threshold against the scenarios, and version the prompt. Includes retrieval favouring actionable sections (Diagnosis, Actions) over overview sections (Purpose, Scope, Summary), seen in the first cluster runs. Evidence from INC0010119 (trace tr-85a11f3a163f24df46e5d1c0e71e3571): every passage sent scored 0.88 to 0.91, so the 0.80 threshold selects nothing and the top six decide; none was the runbook's Diagnosis or Actions; the next steps cited Purpose and Verification, missed the change request to set the heap to 75% of the limit, and suggested scaling out after a heap dump; the cause ranked the cache leak high and heap equal to the limit medium; one gap was not a gap in evidence ("no heap dump taken"). Written (2026-10-27, DD24): service 0.5.0, prompt `enrichment-v2`, policy `policy-v2`. Navigation sections are not searched and the best runbook brings its Diagnosis and Actions, the best resolution its Root cause and Resolution (first the two best documents of any type, but on INC0010126 both were resolutions and the runbook's Actions were missed again); the model's own advice is a separate, low-trust list of suggestions, which never carries a job and is what the note gives when there is no documented fix; gaps are evidence only. Phase 08 checks the documented fix cites the runbook's or a resolution's actions. Still to do: set the threshold from measured scores, including scenario S2's | |

**Exit criteria:** scenarios S1 (level 1 only), S2, S3 and S5 pass, and every automated check in section 9 of the design passes.

**Estimate:** 4 days. The corpus is the largest single task.

**Decision point:** if the selected model fails the prompt injection or citation checks after tuning, try the next candidate from M1.6 before changing the design.

### M5 Level 2 and a second incident family

**Goal:** the work note recommends a catalogued job that an engineer can launch, and a second incident family is added as a content-only change.

| ID | Task | Closes |
|---|---|---|
| M5.1 | Role `remediate_heapdump_restart` and its job template, launchable only by the engineer's account; `reset.yml` clears the heap dumps it leaves (moved from M3.6) | |
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
