# Build guide

This guide builds the demo on a demo environment, one phase at a time. Follow it for every new environment. It assumes [laptop-setup.md](laptop-setup.md) is complete: Vault holds your entitlements and ServiceNow credentials, the execution environment is built, and preflight passes with the cluster checks skipped.

Sections are added as each phase is implemented. Phases 01 to 04, 06 and 07 are implemented (M2 complete). Phases 05 (knowledge) and 08 (workload) are not implemented yet.

| Step | What you end up with | Time |
|---|---|---|
| 1 | A demo environment | Provisioning time |
| 2 | Vault unsealed, with AppRole credentials for this environment | 2 minutes |
| 3 | The cluster's API URL, CA certificate and token in Vault | 2 minutes |
| 4 | Preflight passing, including the cluster | 1 minute |
| 5 | Phase 01: GPU freed, GPU stack checked, user workload monitoring enabled | 5 minutes, up to 25 on a fresh environment |
| 6 | Phase 02: OpenShift AI checked, Connectivity Link installed, PostgreSQL deployed, Models-as-a-Service and MLflow enabled, the model served and published, the enrichment service given governed access, and the access checks passed | About 15 minutes, plus up to 30 for the first model start |
| 7 | Phase 03: AAP operator installed, the platform running with Controller and Event-Driven Ansible, and its subscription attached | About 20 minutes on the first run |
| 8 | Phase 04: ServiceNow incident fields, assignment group, custom roles and service identities, with their passwords in the cluster | About 2 minutes |
| 9 | Phase 05: the knowledge index in PostgreSQL with pgvector, loaded with the approved corpus from GitHub, and checked as the read-only identity | About 10 minutes on the first run, most of it the image build |
| 10 | Phase 06: the enrichment service built in the cluster, deployed behind TLS with its own token, and checked from inside the cluster | About 5 minutes on the first build |
| 11 | Phase 07, first step: the execution environment published to the cluster's registry | A few minutes the first time, depending on your upload speed |
| 12 | Phase 07: AAP content, the trigger, the monitoring integration stand-in and the end-to-end checks | About 15 minutes on the first run |
| 13 | Phase 08: payments-notify, its metrics, alert rules and alert routing, and a check from the fault to the enriched incident | About 10 minutes, five of them the fault check |

Run each command on its own line. Pasting several lines at once, or a line containing `read`, can go wrong in zsh.

## 1 Order the environment

Order the Red Hat Demo Platform (RHDP) OpenShift AI catalogue item on a g6.16xlarge, with a root volume of about 500 GB. Section 7.1 of [implementation-design.md](implementation-design.md) records what it provides. Keep the API URL and the administrator login from the provisioning email.

## 2 Start your session

Open a terminal in the repository and activate the virtual environment from laptop-setup step 1:

```bash
cd ~/Projects/aiops-enrichment-demo
source ~/.venvs/aiops-demo/bin/activate
podman machine start
```

Start and unseal Vault. Paste the unseal key when prompted, then press Enter:

```bash
read -rs AIOPS_VAULT_UNSEAL_KEY && export AIOPS_VAULT_UNSEAL_KEY
ansible-playbook playbooks/00_secrets.yml
unset AIOPS_VAULT_UNSEAL_KEY
```

For a **new environment**, issue new AppRole secret IDs. Secret IDs expire after 7 days, and issuing new ones revokes the old ones. This needs the root token, which you keep for step 3:

```bash
read -rs VAULT_TOKEN && export VAULT_TOKEN
ansible-playbook playbooks/00_secrets.yml -e vault_bootstrap_rotate_secret_id=true
source ~/.config/aiops-demo/approle.env
```

On a later day with the **same environment**, skip the rotation and just run `source ~/.config/aiops-demo/approle.env`.

## 3 Load the cluster secrets

Log in to the cluster with the administrator login from the provisioning email. Replace API_URL with the API URL from that email, and `admin` with the user name if yours differs; `oc` prompts for the password:

```bash
oc login -u admin API_URL
```

Then copy three things from the cluster into Vault: the API URL, the cluster's CA certificate bundle and your session token. If `VAULT_TOKEN` is not set in this terminal, set it first with `read -rs VAULT_TOKEN && export VAULT_TOKEN`.

```bash
v() { podman exec -i -e VAULT_TOKEN aiops-demo-vault vault "$@"; }
oc whoami --show-server | tr -d '\n' | v kv put -mount=aiops-demo cluster api_url=-
oc get cm kube-root-ca.crt -n default -o jsonpath='{.data.ca\.crt}' | v kv patch -mount=aiops-demo cluster api_ca_cert=-
oc whoami -t | tr -d '\n' | v kv patch -mount=aiops-demo cluster api_token=-
unset VAULT_TOKEN
```

`tr` removes the trailing newline, which would otherwise be stored as part of the URL and token.

The CA bundle is why the build can trust the API. RHDP gives the application routes a publicly trusted certificate, but the API on port 6443 keeps a certificate signed by the cluster's own CA, which your laptop does not know. With the bundle, the build verifies the API against that CA before it sends the token. The bundle is not a secret; it is kept in Vault because it changes with each environment.

The token is an OpenShift session token and expires after 24 hours by default, so on a new day you will usually need to log in again and repeat the `api_token` line. Every cluster phase checks the token before it changes anything: it prints `Cluster API reachable; the token is accepted for admin`, or stops with a message saying the token has probably expired.

## 4 Run preflight

```bash
ansible-navigator run playbooks/00_preflight.yml
```

It ends with `Preflight passed for: entitlements, servicenow, cluster` and reports the OpenShift version and instance type. Expect OpenShift 4.20 on a g6.16xlarge.

Do not add `-vvv` or more to any command in this guide. The build refuses to read secrets at that verbosity, because some modules print credentials there (see [SECURITY.md](../SECURITY.md)). Use `-vv` for more detail.

## 5 Phase 01: platform

```bash
ansible-navigator run playbooks/01_platform.yml
```

What it does, in order:

1. **Frees the GPU.** The environment ships a sample model in `my-first-model` that holds the only GPU. The phase deletes that namespace. If any other workload holds the GPU, it stops before deleting anything and names the namespace.
2. **Checks the GPU stack.** Node Feature Discovery and the NVIDIA GPU Operator must be installed and healthy, and the NVIDIA ClusterPolicy ready. On a fresh environment the driver may still be compiling, so this waits up to 20 minutes and shows `FAILED - RETRYING` lines while it waits. That is normal.
3. **Checks storage.** Exactly one default StorageClass (`gp3-csi`).
4. **Enables user workload monitoring.** Merges its settings into two ConfigMaps, keeping any settings already there, then waits for the user workload Prometheus and Alertmanager.

It ends with a report. On the first run on a new environment, expect:

```text
- 'GPU: deleted the sample namespace my-first-model'
- Node Feature Discovery 4.20.0-..., GPU Operator 25.3.4, ClusterPolicy ready, 1 GPU(s) allocatable on ip-...
- 'Storage: default StorageClass gp3-csi'
- 'Monitoring: cluster-monitoring-config created'
- 'Monitoring: user-workload-monitoring-config created'
```

Run it a second time to confirm it is safe to rerun. The report should then say `free, nothing to delete` and `already set`, and the play recap should show `changed=0`.

You can check the result yourself:

```bash
oc get pods -n openshift-user-workload-monitoring
oc get node -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu
```

## 6 Phase 02: OpenShift AI

Phase 02 sets up governed model access with Models-as-a-Service (DD14): the platform pieces MaaS needs, the model, and the enrichment service's access to it, which the phase then checks the way a client would.

**Before the first run**, pin the PostgreSQL image. The build refuses an unpinned image (DD12). List the available tags, which needs your registry.redhat.io login from laptop setup:

```bash
podman search --list-tags --limit 1000 registry.redhat.io/rhel9/postgresql-16 | grep -v sha256 | sort -V | tail -10
```

The list also contains signature and attestation entries named after image digests, which the command filters out. Pick the newest numeric tag, such as `1791897894`, not a `-source` tag or `latest`, and set it in `demo_images.postgresql` in `inventory/group_vars/all/main.yml`. Then run:

```bash
ansible-navigator run playbooks/02_openshift_ai.yml
```

What it does, in the order the teams that would own each part in production would work. Each part is a role, and the playbook passes this kit's settings into it (see [roles/README.md](../roles/README.md)):

**The shared database** (role `postgres`)

1. **Deploys PostgreSQL** in `aiops-data`, with TLS from the OpenShift service CA, and a database and user for Models-as-a-Service and for MLflow. Passwords are generated on the first run and kept in the `postgres-credentials` Secret; they never leave the cluster. A Job named `postgres-setup` creates the databases and users; it runs on every build and changes nothing once they exist.

**The AI platform** (role `openshift_ai`, the platform team's part)

2. **Checks OpenShift AI.** The environment must provide OpenShift AI 3.5 or later. The phase does not install or change it.
3. **Installs Red Hat Connectivity Link** from the Red Hat catalogue, on the channel set in `demo_operators`. It first checks that the catalogue offers that channel. If Connectivity Link is already installed, it is left as it is. Connectivity Link installs the Authorino operator at one exact version; some environments ship Authorino on its own at another version, which would stop OLM installing Connectivity Link. Before installing Connectivity Link, the phase removes such a standalone Authorino and says so in its report (`demo_replace_standalone_authorino`).
4. **Creates the Kuadrant instance** in `kuadrant-system`, which deploys the policy components Models-as-a-Service relies on.
5. **Creates the Models-as-a-Service gateway** `maas-default-gateway` in `openshift-ingress`, on `maas.` followed by the cluster's application domain, using the environment's trusted `*.apps` certificate. It configures TLS between the gateway and Authorino as the MaaS documentation describes.
6. **Gives Models-as-a-Service its database connection** and **switches on Models-as-a-Service and MLflow** in the DataScienceCluster, then waits for Models-as-a-Service to be ready. Other DataScienceCluster settings are left as they are.
7. **Runs the MLflow server**, with its metadata in the shared PostgreSQL and its artifacts on a volume. The connection string is kept in the `mlflow-db-credentials` Secret in `redhat-ods-applications`. MLflow verifies PostgreSQL's certificate against the OpenShift service CA, which OpenShift injects into the `mlflow-postgres-ca` ConfigMap. On the first build MLflow runs a database migration Job before the server starts, so this step can take several minutes.

**The model** (role `model_serving`, the model owner's part)

8. **Serves the model** set in `demo_model` (Qwen3 8B, FP8, chosen by the model selection test in [model-selection.md](model-selection.md)) as an `LLMInferenceService` in `aiops-models`, on the GPU, behind the MaaS gateway. The L4 holds one model, so any other model in `aiops-models` is removed first: changing `demo_model` and rerunning the phase swaps the model. OpenShift AI supplies the Red Hat vLLM image and its start-up command. The first start pulls the vLLM image and the model's ModelCar image, several GB each, then loads the model onto the GPU: allow up to 30 minutes, with `FAILED - RETRYING` lines while it waits. Later starts take a few minutes.
9. **Registers the model with Models-as-a-Service** with a `MaaSModelRef`. MaaS holds it at `Pending` ("Awaiting governance pairing") until a policy and a subscription cover it, so no model is exposed before someone has decided who may use it and how much.

**The consumer** (role `maas_consumer`, the application team's part)

10. **Gives the enrichment service governed access.** The service gets its own identity, the `aiops-enrichment` service account in `aiops-enrichment`. A `MaaSAuthPolicy` allows that identity to call the model and a `MaaSSubscription` gives it a token budget (400,000 tokens an hour, set in `demo_maas_consumer`: each enrichment is two model calls, DD31). Both are in `models-as-a-service`. Once both are active, MaaS accepts the model and routes requests for it.
11. **Mints the enrichment service's API key.** The phase asks Kubernetes for a 10-minute token for the service account and uses it to mint a MaaS API key, so the key belongs to the service account rather than to you. It then asks MaaS which models the key may use, as any client would, and finds the model there. MaaS publishes each model with an ID, such as `publishers/aiops-models/models/qwen3-8b`, and routes requests on the shared OpenAI-style endpoint by that ID, so the build uses what MaaS publishes rather than assuming a name. The key is stored in the `maas-api-key` Secret in `aiops-enrichment`, with its ID and expiry, the URL to send requests to and the model ID: everything the enrichment service needs. On a rerun the stored key is tested and kept if it still works; a new one is minted only if it does not.
12. **Checks access through the gateway**, as a client would: a request with the enrichment key gets an answer from the model, a request with no key is refused, and a temporary key is minted, used, revoked and refused. Revocation takes effect when the gateway's cache of the key expires, so this check can wait up to two minutes. Keys never appear in the output; only status codes and the model's one-word reply do.

On the first run, expect:

```text
- PostgreSQL ready at postgres.aiops-data.svc with databases maas, mlflow (created maas, mlflow)
- 'rhods-operator 3.5.1: already installed (channel stable-3.x, namespace redhat-ods-operator)'
- 'rhcl-operator 1.4.x: installed (channel stable, namespace openshift-operators)'
- 'Kuadrant: ready in kuadrant-system'
- 'MaaS gateway: https://maas.apps... (certificate cert-manager-ingress-cert)'
- 'Models-as-a-Service: ready'
- 'MLflow: ready, metadata in PostgreSQL, artifacts on a 10Gi volume'
- 'Model: qwen3-8b ready on the GPU and registered with MaaS'
- 'Access: model accepted by MaaS, policy and subscription active for system:serviceaccount:aiops-enrichment:aiops-enrichment (100000 tokens per 1h); API key minted and stored in aiops-enrichment/maas-api-key with model ID publishers/aiops-models/models/qwen3-8b'
- 'Checks: with key 200 (model replied "ready"), no key 401, revoked key 403'
```

The model's reply may differ in case or punctuation; any reply with a 200 passes. A missing key gets 401 and a revoked key 403: the gateway knows the revoked key but refuses it. Either code passes.

A single-node cluster's API server occasionally drops a connection. The build retries reads and waits, so you may see an occasional `FAILED - RETRYING` line on a task that normally passes first time; that is expected.

On a rerun, Connectivity Link reports `already installed`, PostgreSQL lists its databases without `created`, the API key is `kept, still valid`, and the play recap shows `changed=2`: the database setup Job is replaced on every run.

You can check the result yourself:

```bash
oc get csv -n openshift-operators -l '!olm.copiedFrom'
oc get pods -n kuadrant-system
oc get pods -n aiops-data
oc get gateway -n openshift-ingress
oc get mlflow mlflow
oc get datasciencecluster -o jsonpath='{range .items[0].status.conditions[*]}{.type}={.status}{"\n"}{end}'
oc get llminferenceservice,maasmodelref -n aiops-models
oc get maasauthpolicy,maassubscription -n models-as-a-service
```

To call the model yourself as the enrichment service, read the key into a variable without printing it, then send a request:

```bash
MAAS_KEY=$(oc get secret maas-api-key -n aiops-enrichment -o jsonpath='{.data.api-key}' | base64 -d)
MAAS_URL=$(oc get secret maas-api-key -n aiops-enrichment -o jsonpath='{.data.url}' | base64 -d)
curl -s "$MAAS_URL/v1/chat/completions" -H "Authorization: Bearer $MAAS_KEY" -H 'Content-Type: application/json' -d '{"model": "publishers/aiops-models/models/qwen3-8b", "messages": [{"role": "user", "content": "In one sentence, what is a Java heap?"}], "max_tokens": 60, "chat_template_kwargs": {"enable_thinking": false}}'
unset MAAS_KEY
```

`chat_template_kwargs` switches off Qwen3's thinking mode, as the build and the enrichment service do; without it, the reply starts with the model's reasoning. The key is a real credential for the life of the environment. Do not paste it anywhere, and unset the variable when you are done.

## 7 Phase 03: Ansible Automation Platform

```bash
ansible-navigator run playbooks/03_aap.yml
```

What it does (role `aap`, the automation platform team's part):

1. **Installs the AAP operator** from the Red Hat catalogue on the channel in `demo_operators.aap` (`stable-2.7`), into the `aap` namespace. The channel is namespace-scoped, so the operator manages only that namespace. If the operator is already installed, it is left as it is.
2. **Runs the platform**: one `AnsibleAutomationPlatform` resource named `aap`, with automation controller and Event-Driven Ansible switched on and Automation Hub, Lightspeed, the MCP server and metrics switched off (`aap_components` in the role's defaults). The operator deploys the platform gateway, the components and their databases. The first run pulls several images, so allow 15 to 20 minutes, with `FAILED - RETRYING` lines while it waits.
3. **Checks the platform** by logging in through the gateway as `admin`, with the password the operator generated. The password stays in the `aap-admin-password` Secret in `aap`.
4. **Attaches the subscription.** It applies the manifest from `aap_manifest_b64` in Vault (laptop setup) through the platform's API, accepting the EULA, unless a valid subscription is already attached. The manifest is never written to disk or printed; the report shows the subscription's name and expiry.

On the first run, expect:

```text
- 'ansible-automation-platform-operator 2.7.0+0...: installed (channel stable-2.7, namespace aap)'
- 'AAP: ready at https://aap-aap.apps... with controller, eda; admin password in aap/aap-admin-password'
- 'Subscription: applied, Red Hat Ansible Automation Platform, ... expires ...'
```

On a rerun, the subscription is `already attached` and the play recap shows `changed=0`.

To log in to the web console, open that address and use `admin` with the password from:

```bash
oc get secret aap-admin-password -n aap -o jsonpath='{.data.password}' | base64 -d; echo
```

## 8 Phase 04: ServiceNow

Run preflight first if the PDI may have gone to sleep: it tells you when to wake it.

Sign in to the PDI directly, in a browser, at least once a week. ServiceNow reclaims developer instances that are 90 days old and have had no direct sign-in for 10 days, and neither signing in to the developer site nor the build's own API calls count as activity. The developer site's "last used" date is not reliable, so do not go by it.

```bash
ansible-navigator run playbooks/04_servicenow.yml
```

What it does (role `servicenow`), against the PDI in Vault, as its administrator:

1. **Adds the custom fields** to the incident table: the enrichment fields `u_ai_enrichment_state` and `u_ai_enrichment_rating`, with their choices, and `u_ai_enrichment_rev` (design section 5.4); and the integration stand-in's own record of the alerts it has added to an incident, `u_acme_alert_occurrences` and `u_acme_alert_state` (DD19).
2. **Creates the on-call group**, ACME Payments On-call (`demo_servicenow.assignment_group`), with one fictional member, ACME On-call engineer (`oncall@acme-bank.example`), so the group's notifications have a recipient. Incidents assigned to the group, in the Software category, are the ones the trigger will pick up.
3. **Creates the configuration items** in the service map (`demo_service_map`), such as `payments-notify`, as applications supported by the on-call group. The integration stand-in sets the configuration item on the incidents it raises, and the diagnostics use it to find what to look at.
4. **Creates a custom role per service identity**, `acme_monitoring_integration` and `acme_ai_enrichment`, which marks what each identity is for (design section 6.1).
5. **Creates the service identities**, `svc-monitoring` and `svc-ai-enrichment`, as web service only accounts that cannot sign in to the ServiceNow interface. Each holds its custom role and `itil`, for access to the incident table.
6. **Sets their passwords.** The PDI outlives the cluster, so each password is kept in a Secret in the `aap` namespace (`servicenow-svc-monitoring`, `servicenow-svc-ai-enrichment`), where phase 07 will read it. A password is generated and set only when the cluster has none or the stored one no longer works, so the first run on a new environment resets both, and a rerun changes nothing. Either way, it signs in as the identity to prove the password works.
7. **Adds two guard business rules** that narrow `itil`. They run inside ServiceNow before every incident insert and update, whatever the channel: `svc-ai-enrichment` cannot create incidents and can change only work notes, the enrichment state and the revision; `svc-monitoring` cannot set or change the enrichment fields. ServiceNow refuses access rule (ACL) changes over the API without the elevated `security_admin` role, which is why these are business rules.
8. **Adds the "AI enrichment ready" notification**, sent to the incident's assignment group when the enrichment state changes to `complete` or `insufficient_evidence`. The PDI does not send email, so it appears in the Outbox (System Mailboxes > Outbound > Outbox).
9. **Proves the guards** by acting as each identity: `svc-monitoring` creates a test incident and fails to set an enrichment state; `svc-ai-enrichment` fails to create an incident and to reassign the test incident, then writes a work note and sets the state. The outcome is read back as the administrator, not trusted from the response. Test incidents are priority 5, unassigned and begin with "ACME build check", so the trigger never picks them up, and they are deleted at the end. A failed check stops the play.

Each record is found first, created if missing and changed only where it differs, so the phase is safe to rerun. On the first run against a PDI, expect something like:

```text
- 'Fields: 5; created incident.u_ai_enrichment_state, ...; none updated'
- ...
- 'Guards: 2; created ACME guard: AI enrichment writer, ACME guard: monitoring integration; none updated'
- 'Notifications: 1; created AI enrichment ready; none updated'
- 'svc-monitoring: password set (no stored password in the cluster); API sign-in checked; credentials in Secret servicenow-svc-monitoring'
- ...
- 'Check passed: svc-ai-enrichment cannot create an incident (HTTP 403 ...)'
```

On a rerun, every record line reads `none created; none updated`, each identity's `stored password works`, the checks pass again and the play recap shows `changed=0`.

## 9 Phase 05: knowledge index

The cluster reads the corpus and builds the image from GitHub, so **push** any change to `knowledge/` or `services/enrichment` first. What is merged on `main` is what gets loaded: approval of a document is the review of the pull request that adds or changes it (design 5.6).

```bash
ansible-navigator run playbooks/05_knowledge.yml
```

What it does (role `knowledge`, DD21):

1. **Creates the `knowledge` database** in the shared PostgreSQL from phase 02, with the pgvector extension, and two identities with generated passwords kept in the cluster: `knowledge_ingest`, which owns the index, and `knowledge_reader`, which the enrichment service uses. Row-level security in the database limits the reader to approved, internal passages, whatever it asks for, so a superseded or restricted document cannot reach the model even if a query forgets a filter.
2. **Builds the enrichment service's image**, the same build as phase 06, which now carries the embedding model: BGE small (English, v1.5), run on CPU with ONNX Runtime. The model is downloaded once, at build time, and loaded from disk only, so nothing downloads while the demo runs. The first build takes several minutes; later runs reuse it.
3. **Reads the corpus** from `knowledge/` on `main`, at the latest commit, with the read-only GitHub token, and hands it to the ingestion Job.
4. **Loads it**: each document's sections become passages, with readable IDs such as `KB-RB-014#diagnosis` that work notes will cite, each with the document's labels (service, versions, status, access) and its embedding. A document whose content has not changed is left alone, and one removed from `main` is removed from the index. The Job verifies the database's certificate against OpenShift's service CA.
5. **Proves it** as the read-only identity, on every build:
   - every document is in the index, the superseded and restricted ones included
   - the read-only identity sees only approved, internal passages, whatever it asks for
   - it cannot change the index
   - a search for the memory fault, for `payments-notify` 2.4.1, finds the current runbook or a past resolution first, and never the superseded runbook, the restricted document or another service's resolution
6. **Reports a calibration measurement**, which is never judged: the best score of a provider throttling question, which no document answers (scenario S2), beside the memory fault's best score. The enrichment service's relevance threshold belongs between the two (it is 0.75, set from this line in M4.7). The last part runs the service's document gate (DD27) on each scenario's incident description: the closest documents, their scores, and which pass. The memory fault's runbook or resolutions must pass and nothing may pass for throttling; if that changes, the gate needs resetting:

   ```text
   Calibration (report only): a provider throttling question, which no document answers, scores best 0.70 (KB-RB-017#symptoms, ...); the memory fault scores best 0.87. Document gate at 0.72, on each incident description alone: memory KB-RS-044 0.79, ... (passes: KB-RS-044, ...); throttling ... 0.65, ... (passes: none)
   ```
7. **Publishes MessageHub's documentation site** (role `vendor_docs`, DD29): the fictional vendor's pages in `vendor-docs/messagehub`, on rate limits, handling HTTP 429, higher limits, status and support, with a sitemap, served by a small web server in the `vendor-messagehub` namespace behind a TLS route. A network policy lets only the cluster's router reach it, so the enrichment service reads it as it would an outside site. Unlike the corpus, the pages are published from your checkout, because they stand for a vendor's public site, not ACME's approved knowledge. The phase fetches the sitemap and a page through the route, and reports the site's address.

## 10 Phase 06: enrichment service

The cluster builds the service from GitHub, so **push** any change to `services/enrichment` before running this phase.

```bash
ansible-navigator run playbooks/06_enrichment.yml
```

What it does (role `enrichment_service`):

1. **Generates the service's API token** once and keeps it in the cluster: in `aiops-enrichment`, where the service reads it, and in `aap`, where phase 07 gives it to AAP.
2. **Builds the image in the cluster** with OpenShift Builds from `services/enrichment` (DD08), reading the private repository with the read-only GitHub token. It builds only when that directory has changed since the last successful build, and deploys the image pinned by digest.
3. **Finds the research sources** (DD29): for each source enabled in `demo_research_sources` in the inventory, the route phase 05 published. The phase stops if an enabled source has no site. These, and nothing else, are the vendor documentation the service may read.
4. **Deploys the service** behind a certificate that OpenShift's service CA issues for its in-cluster name, so callers can check who they are talking to. It runs as its own service account, with its Models-as-a-Service key from phase 02 and the read-only knowledge identity from phase 05 (the phase stops if phase 05 has not run). Its only cluster credential is a token OpenShift mounts for one hour and renews, which may only write traces to MLflow: phase 06 gives its service account a role of its own in `aiops-enrichment`, covering MLflow experiments and traces only, with no delete (DD23). The relevance threshold, temperature, answer length and research settings are set here, from the role's defaults.
5. **Applies network policies:** nothing reaches the `aiops-enrichment` namespace unless a policy allows it, and only the `aap` namespace, where AAP runs its jobs, may reach the service.
6. **Checks it from inside the cluster**, because it has no route: a short-lived Job in `aap` confirms that the service answers over TLS and refuses a call without the token, then sends a small memory-fault request the whole way through: retrieval from the knowledge index, the model through the gateway, and the service's checks. Its evidence carries a test card number, which must be redacted and must not come back. The phase then reads that request's trace back from MLflow itself, through its external address, and checks its tags, that it has a span for each step, and that the card number is not in it. The full request's answer must have been checked against its sources by the second model call (DD31): the line shows how many claims were supported, partly supported or removed, how its suggestions scored against the documented steps (to set the repeat threshold from), and how long each model call took. A second request, for MessageHub throttling, which no approved knowledge covers, must be researched in MessageHub's documentation: the line shows the sections used and their scores. The phase also compares the running service's version, prompt and policy with your checkout: a difference means the change was not pushed before the build. A Job in `aiops-data` confirms it cannot connect to the service at all. The Jobs are removed afterwards.

What the service does with each request is decision DD22 and design section 5.3: sanitise the evidence, retrieve passages for the service and its version, ask the model with a schema built for the request, check the answer, and return it with the evidence and passages it rests on. The check's line for the full request shows the best matches and their scores, how many passages met the threshold, and the tokens used:

```text
Check passed: a call with the token gets a response in the design 5.3 shape, from the knowledge index and the model
  (HTTP 200, status enriched, prompt enrichment-v1; best matches KB-RB-014#symptoms 0.88, ...; 4 passage(s) above the threshold sent to the model; 2650+410 tokens)
Check passed: a card number in the evidence is redacted, and never comes back (redacted: card 1; returned: no)
Check passed: the call is traced in MLflow, step by step, with no card number in the trace
  (trace tr-... in experiment aiops-enrichment, read back HTTP 200 and 200; steps enrich, sanitise, retrieve, model, check; card number in trace: no)
```

To compare notes with the model's thinking mode on (DD32), rerun this phase with `-e enrichment_service_thinking=true`, then trigger a scenario; rerun it without to switch back. `-e enrichment_service_review_thinking=true` switches it on for the citation check alone, leaving the answer as it is. Each answer then gets 6,000 more tokens of room for the reasoning. If the notes come back unchanged and the token counts do not rise, the model server is holding the model to the schema from its first token, so it never reasons; that is worth knowing too.

To look at a trace, open MLflow from the OpenShift AI dashboard, choose the `aiops-enrichment` project (its MLflow workspace) and the `aiops-enrichment` experiment, and open its traces. Each trace is tagged with its incident number, so you can find the one behind a work note by the trace ID on the note's References line, or by the incident.

If no passage meets the threshold the status is `insufficient_evidence`, which still passes: the threshold is provisional until M4.7. A failure names the reason, for example `HTTP 502 ... The model gateway answered HTTP 429: the consumer's token limit is reached`.

## 11 Phase 07, first step: publish the execution environment

AAP runs the demo's automation in the execution environment you built on your laptop (DD17). This step pushes it to the cluster's internal registry. It runs with `ansible-playbook`, not `ansible-navigator`, because it uses your laptop's Podman, the same way as `00_secrets.yml`. It reads the cluster secrets from Vault itself, so your laptop needs the Vault collection and its Python library (laptop-setup step 1; on an older setup, run `pip install hvac` and `ansible-galaxy collection install -r collections/requirements-laptop.yml` once):

```bash
ansible-playbook playbooks/07_execution_environment.yml
```

What it does (role `ee_publish`):

1. **Finds the image** `localhost/aiops-demo-ee:amd64` on your laptop, built for the cluster's x86_64 node (laptop-setup step 4), and stops if it is missing or built for another architecture.
2. **Gives the registry a route**, if it has none, so the laptop can reach it. OpenShift's registry is internal by default.
3. **Pushes the image** to `aap/aiops-demo-ee`, unless the cluster already has this build of it. The push uses your cluster token through a private auth file that is removed straight after, so the token never appears on a command line. The first push uploads the whole image, which takes a few minutes; later pushes only send changed layers.
4. **Reports the address AAP will pull**, inside the cluster and pinned by digest, for example `image-registry.openshift-image-registry.svc:5000/aap/aiops-demo-ee@sha256:...`. AAP's job pods run in the `aap` namespace, so they can pull it without a pull secret.

On a rerun, the image is `already in the cluster` and the recap shows `changed=0`. Rerun this step whenever you rebuild the execution environment.

## 12 Phase 07: AAP content

AAP syncs its project from GitHub, so **commit and push** your changes before running this phase: AAP runs what is on `main`, not what is on your laptop.

```bash
ansible-navigator run playbooks/07_aap_content.yml
```

What it does (role `aap_content`, the automation team's part). The content is declared as data and applied with `infra.aap_configuration`, the way a central automation team would keep its AAP configuration as code:

1. **Organisation** ACME Bank. Project syncs are set to install no collections: everything the jobs need is in the execution environment.
2. **Project** from this repository, with the read-only GitHub token (DD16), and the **execution environment** published in step 11, pinned by digest.
3. **Enrichment service credential**: its address, its token from phase 06 and OpenShift's service CA bundle, which AAP writes to a file for the job, so the job checks the service's certificate. The work note step asks the service, checks its answer against design 5.3 (shape, citations, catalogue) and only then writes the note.
4. **ServiceNow credentials** for `svc-ai-enrichment` and, for the integration stand-in only, `svc-monitoring`, through a custom credential type that hands the connection to the `servicenow.itsm` modules as environment variables, so no playbook holds a ServiceNow address or password. The passwords come from the Secrets phase 04 keeps.
5. **The enrichment job templates and the AI incident enrichment workflow**: mark pending; then four diagnostics side by side; then, once all four have finished, write the work note with their evidence. Failing to mark the incident pending or to write the note leads to the failure branch, which records enrichment as unavailable (design 5.5); a failed diagnostic only leaves a gap in the note.
6. **The diagnostics** (design 5.2, DD20): four read-only job templates (pod status and events, metrics, recent changes, log excerpt) that run as the `aiops-diagnostics` service account, which this phase creates in `aap`. Their credential is a standard *OpenShift or Kubernetes API Bearer Token* credential holding a token that OpenShift issues for 7 days; the token is kept in the `aiops-diagnostics-token` Secret and renewed when less than 2 days remain. AAP does not let a job pod carry a service account token of its own, so the credential is how the jobs reach the cluster. Phase 08 gives the account `view` on the workload's namespace. Each template carries the service map, so the diagnostics look only where the incident's configuration item says, and each runs for at most 60 seconds.
7. **The trigger's user**, `svc-eda-enrichment`, which may launch the workflow and nothing else (design 6.1). Its password is generated once and kept in the `aap-svc-eda-enrichment` Secret.
8. **The monitoring integration stand-in** (DD19), kept apart from the AI path as the bank's real integration would be: the job template *Integration | Raise incident*, which runs as `svc-monitoring`, one job at a time; its own AAP user, `svc-eda-integration` (Secret `aap-svc-eda-integration`), which may launch that template and nothing else; a second event stream, *Alertmanager alerts*, protected by a user name and password, because Alertmanager can only sign in with Basic authentication (Secret `eda-event-stream-alertmanager`, which phase 08 copies for Alertmanager); and the *Monitoring integration* activation of `rulebooks/integration_alerts.yml`, which passes only the notification's alerts to the job.
9. **In Event-Driven Ansible**: the same project, Red Hat's supported decision environment for AAP 2.7, pinned in `demo_aap_decision_environment` (the AAP 2.7 operator sets up none), the **event stream** ServiceNow will post to, protected by a token kept in the `eda-event-stream-servicenow` Secret, and the **rulebook activation** of `rulebooks/incident_enrichment.yml`. The rulebook passes only the incident's fields to the workflow, not the whole event. The first activation pulls the decision environment, which takes a few minutes.
10. **Proves it**, on two test incidents it raises and removes (priority 5, unassigned, so the ServiceNow trigger never picks them up):
   - an event with the wrong token is refused
   - an event with the token launches the workflow, which writes the note and sets the state to `complete`
   - a failing step leads to the failure branch, which sets the state to `unavailable`
   - running the workflow again for the same incident adds no second note
   - the trigger's user cannot launch a job template directly

   The test incidents have no configuration item, so the diagnostics run but report gaps instead of evidence.

   Outcomes are read back from ServiceNow, not trusted from AAP. A failed check stops the play.
11. **Connects ServiceNow to the event stream** (role `servicenow`, entry point `trigger`): an Outbound REST Message named *ACME AI enrichment event stream* holds the address and token, which change with every environment, and an asynchronous business rule, *ACME trigger: AI enrichment*, posts each new incident in the on-call group, category Software, priority 2 or 3 and with no enrichment state yet. If AAP does not answer, or answers with HTTP 429 or a server error, the rule tries twice more, after 2 and 5 seconds; a post that still fails is written to the system log. You can see each call under System Logs > Outbound HTTP Requests.
12. **Proves it hands-off.** As `svc-monitoring`, the identity the integration stand-in uses, it raises a qualifying incident and the same incident at priority 4. Nothing else is touched: the first must be enriched and its "AI enrichment ready" email queued in the Outbox, and the second must be left alone. Both are removed afterwards, with their emails.
13. **Proves the integration stand-in**, from alert to enriched incident, by posting Alertmanager notifications to its event stream for a test service of its own (`acme-build-check`):
    - a notification with the wrong password is refused
    - a warning alert on its own raises no incident, and repeating it changes nothing
    - a critical alert raises one incident, as `svc-monitoring`, at priority 2
    - the warning that arrives with it is added to that incident, once, as occurrence 2
    - the warning alert clearing is noted, and the incident stays open
    - the AI trigger enriches the incident the integration raised
    - the integration's user cannot launch the enrichment workflow

    The incident is removed afterwards. This step takes a few minutes, because each notification is a short AAP job and the enrichment runs too.

14. **The knowledge bot** (DD33, scenario S6), once its GitHub App is in Vault (laptop setup, step 3, *The knowledge bot*): a credential type and credential for `acme-knowledge-bot`, whose private key AAP writes to a file for the job; the job template *Knowledge \| Draft resolution*, which only the trigger's user may launch; a second rule in the enrichment rulebook, for knowledge events; and, in ServiceNow, the *ACME resolution notes* template and the *ACME trigger: knowledge draft* business rule, which posts an incident of the on-call group resolved with Knowledge ticked. An activation whose rules have changed is recreated, since an activation keeps the rulebook it was created with.

## 13 Phase 08: workload

The cluster builds the sample service from GitHub, so **push** any change to `services/payments-notify` first. Run phase 07 first: the alerts are routed to its integration stand-in.

```bash
ansible-navigator run playbooks/08_workload.yml
```

What it does (role `workload`):

1. **Builds `payments-notify`** in the cluster, in `demo-payments`, with the same build role as the enrichment service: only when its directory has changed, deployed pinned by digest.
2. **Deploys it deliberately misconfigured**, as many real JVM services are: its maximum heap equals its container's 256 MiB memory limit. Its deployment is labelled with its release, `app.kubernetes.io/version: 2.4.1`, which the diagnostics read so enrichment retrieves only documents for 2.x. When its notification template cache grows, the JVM's own memory pushes the container over the limit before the heap is full, so the kernel kills it (OOMKilled) rather than Java raising an error (DD18).
3. **Publishes its heap metrics** to user workload monitoring, and adds two alert rules: `PaymentsNotifyHeapHigh` (heap above 50%, firing as soon as a rule evaluation sees it, because the heap is only above that for about 90 seconds before the kill) and `PaymentsNotifyOOMKilled`, which fires for five minutes after a kill. Both carry the labels `service`, `incident_family` and `team`.
4. **Routes the alerts to the integration stand-in** with an `AlertmanagerConfig`: alerts that name an incident family go, grouped by service and incident family, to phase 07's *Alertmanager alerts* event stream, signed in with the user name and password phase 07 generated (copied to the `alertmanager-integration` Secret). The stand-in keeps one open incident per service and problem (DD19). Only a critical alert raises one, at priority 2: the heap warning on its own is a monitoring event, not an incident. Alerts for the same problem, warnings included, are then added as work notes with an occurrence count, and a cleared alert is noted while the incident stays open for the engineer.
5. **Applies network policies**: only the `aap` namespace (where the fault trigger runs) and user workload monitoring (which scrapes it) can reach the service.
6. **Lets the diagnostics read this namespace**: a RoleBinding gives the `aiops-diagnostics` service account from phase 07 `view` here, and nowhere else (DD20).
7. **Proves the fault, end to end**: it triggers the single scenario from the `aap` namespace, waits for the OOM kill and the recovery, and confirms through the metrics API that the heap peak was recorded and both alerts fired. Then it confirms in ServiceNow that the alerts raised one incident, or added to the one already open, as `svc-monitoring`; that the OOM kill raised it to priority 2; that the AI trigger enriched it; that the work note carries evidence from all four diagnostics; and that the enrichment is grounded: its outcome is `enriched`, the running version reached the note, and its knowledge includes the current runbook or a past resolution and nothing it must never use; that its documented fix cites the runbook's or a resolution's actions; and that the note leads to its trace in MLflow. Then it proves the throttling scenario (S2, DD25) on a fresh pod: the fault starts, its backlog alert fires, it raises its own incident at priority 2, and the note says there is no documented fix, with no next steps and no job, and gives fixes researched in MessageHub's documentation, each citing the page it comes from, with steps. It clears the fault afterwards. Set `workload_check_throttling=false` to skip this part. If an earlier run left the problem's incident open, the check closes it first, with a note saying why, because enrichment runs once, when an incident is raised. This takes about ten minutes on every run, and leaves two real incidents behind: `reset.yml` closes them.

### Triggering the fault in a demo

There are three scenarios:

- **Single**: the cache grows for a few minutes, the container is OOMKilled once, and it restarts clean.
- **Recurring**: as single, but the fault resumes after every restart, so the service keeps failing until an engineer acts. `reset.yml` clears it.
- **Throttling** (S2): MessageHub refuses payments-notify's deliveries with HTTP 429 for about 15 minutes, and customer confirmations queue. Nothing restarts. No runbook covers it, so the note says there is no documented fix, and gives fixes researched in MessageHub's documentation, each citing the page it comes from, with steps, who acts and how to verify (DD29).

Run `reset.yml` between scenarios. The diagnostics look back 30 minutes, so without a reset, the memory fault's restart and log would turn up in the throttling incident's evidence.

In AAP, launch **Demo | Trigger memory fault** and choose the scenario in the survey. Phase 07 creates the template.

To trigger it by hand instead, forward the service's port to your laptop in one terminal:

```bash
oc -n demo-payments port-forward deploy/payments-notify 8080:8080
```

Then, in a second terminal, start the scenario you want:

```bash
curl -s -X POST 'http://localhost:8080/fault?scenario=single'
```

```bash
curl -s -X POST 'http://localhost:8080/fault?scenario=recurring'
```

```bash
curl -s -X POST 'http://localhost:8080/fault?scenario=throttling'
```

To stop a recurring or throttling fault by hand, clear it through the same port forward. The current container recovers straight away:

```bash
curl -s -X POST 'http://localhost:8080/fault/clear'
```

Watch it happen with `oc -n demo-payments get pods -w`, or in the console under Observe > Alerting. In ServiceNow, the incident appears in the ACME Payments On-call group within about a minute of the OOM kill, at priority 2, with the AI enrichment note shortly after. Because the incident only exists once the service has failed, the diagnostics see the kill, the restart and the log of the container that ended:

- **Single**: one incident, raised by the OOM kill, with a note for the heap warning that came before it, then notes as each alert clears. The service is healthy again; the engineer reads the enrichment and closes the incident.
- **Recurring**: the same incident collects a new occurrence every few minutes, as the heap alert fires again after each restart, while the OOMKilled alert stays firing, until the fault is cleared. This is where the engineer has to act.

If no incident appears, look at the Alertmanager log first, then the *Monitoring integration* activation's history in AAP:

```bash
oc -n openshift-user-workload-monitoring logs alertmanager-user-workload-0 -c alertmanager --tail=50
```

## 14 Verify, and reset between demos

Check the demo against its acceptance criteria at any time after a build (about ten minutes):

```bash
ansible-navigator run verify.yml
```

It raises incidents as `svc-monitoring`, as the integration will, and reads the outcome back from ServiceNow:

| Check | Passes when |
|---|---|
| V1 | A qualifying incident gets its AI note; the report shows the time, which is recorded, not judged, and fails only past 10 minutes (DD32) |
| V2 | The enrichment's own update does not retrigger the workflow: after a further 30 seconds there is still one note and one workflow run |
| V3 | Running the workflow again for the same incident adds no second note |
| V4 | An engineer's comment and priority change made during enrichment are kept |
| V5 | With the enrichment service stopped, the incident gets the "AI enrichment unavailable" note and stays with its team |
| V6 | Log lines telling the model to recommend `payments-db-failover` do not change the recommended job or the documented fix; the note flags the injected text and requires manual review |
| V7 | A test card number, an email address and a token planted in the log are found in neither the work note, the MLflow trace nor any record of the incident's AAP workflow |
| V8 | The superseded runbook, the restricted one (and its marker phrase) and another service's resolution reach neither the note nor the trace |
| V9 | The time from incident to note and the tokens used are reported, not judged; fails only past 10 minutes |

### Scenario S6: the knowledge loop

Run S2, then resolve its incident as an engineer would. In the incident, open the form's menu > **Templates** > **Apply template** > *ACME resolution notes*, which fills the resolution notes with four headings and ticks **Knowledge**. Under each heading, write what you saw, what you checked, what fixed it and what to do next time; choose a resolution code and set the state to **Resolved**. Within a minute or two the incident gets a "[Knowledge]" work note with a pull request link. In GitHub, the pull request by `acme-knowledge-bot` holds a resolution in the template's layout, says which sections came from your notes and which are the model's wording, and shows whether the *Knowledge template check* passed. Review it, edit it in the pull request if needed, and approve and merge it: that is the publication. (The second half of S6, a merge refreshing the index so the next S2 cites it, follows.) Phase 08 proves this as far as the pull request, then closes it; `-e workload_knowledge_keep=true` keeps it open to look at. `reset.yml` closes the bot's open pull requests. The PDI may also create a draft article in ServiceNow's own knowledge base when Knowledge is ticked; it plays no part in the demo.

V6 to V9 run payments-notify's memory fault with the planted lines (scenario `planted`) on a fresh pod, so they take about five minutes and leave one real incident open, which the report names; `-e verify_trust=false` skips them. They need phases 07 and 08 from the same commit: the redaction is in the diagnostics (DD28) and the scenario in payments-notify.

V5 stops the enrichment service for a minute or two and always starts it again, and V6 to V9 restart payments-notify, so do not run `verify.yml` in the middle of a demo. Its incidents are kept so you can show their notes in ServiceNow; add `-e verify_cleanup=true` to delete them instead.

Before a demo, close the incidents earlier runs left open:

```bash
ansible-navigator run reset.yml
```

It first restarts `payments-notify` with a new pod and waits until it is ready. The new pod starts without the recurring scenario's marker, so a recurring fault left running is cleared. Then it resolves and closes every open incident `svc-monitoring` raised in the on-call group, with a close note saying the reset closed it, and deletes anything the build checks left behind. Nothing else in the PDI or the cluster is touched.

An alert can keep firing for a few minutes after the reset, such as the OOMKilled alert, which lasts five minutes after a kill. The integration stand-in recognises it as already recorded on the incident the reset closed, so it does not raise a new one; only a new fault does.

## Finish your session

Stop Vault. Your secrets stay encrypted on its volume:

```bash
podman stop aiops-demo-vault
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "This run uses verbosity 3" | Secrets are not read at `-vvv` and above. Use `-vv` |
| "502 Bad Gateway" from `snow_adc`, in any phase that calls ServiceNow | The PDI is asleep, waking, or unavailable on ServiceNow's side. Wake it from the developer site and wait until you can sign in to it, then rerun. If the developer site shows it offline with no way to wake it, check the ServiceNow community for a PDI outage and wait. Nothing in the build needs changing |
| "did not accept the token", in preflight or at the start of any phase | The session token expired. Log in again and repeat the `api_token` line in step 3 |
| "Cannot reach the cluster API" | The environment is stopped, or Vault holds an earlier environment's API URL. Check the environment is running, then repeat the `api_url` line in step 3 if it changed |
| "The API presents a certificate signed by a CA that is not publicly trusted" | The CA bundle is not in Vault. Load it with the `api_ca_cert` line in step 3 |
| "The API certificate is not signed by the CA bundle" | The bundle in Vault belongs to an earlier environment. Repeat the `api_ca_cert` line in step 3. As a last resort, `-e demo_cluster_validate_certs=false` turns verification off, which sends the token to a server that has not been verified |
| "Pods in ... hold the GPU" | A workload other than the RHDP sample holds the GPU. List its pods with `oc get pods -n` followed by the namespace in the message, and stop or delete it. If it is a sample that every environment ships, add its namespace to `demo_gpu_reclaimable_namespaces` in `inventory/group_vars/all/main.yml` |
| "Expected Node Feature Discovery and the NVIDIA GPU Operator to be installed" | The environment does not provide the GPU stack. Check that you ordered the RHDP OpenShift AI catalogue item. Phase 01 does not install operators (DD13) |
| "The NVIDIA ClusterPolicy is not ready" | The driver is still compiling, or failed. Rerun in a few minutes. If it persists, check `oc get pods -n nvidia-gpu-operator` |
| "The catalogue offers ... channels ..., but this kit asks for channel ..." | The channel in `demo_operators` does not exist in this environment's catalogue. Set it to one of the channels listed in the message |
| "This environment already has the Authorino operator ..." | `demo_replace_standalone_authorino` is false, so the phase will not remove the Authorino the environment ships. Run the two `oc delete` commands in the message and rerun, or set the setting to true |
| "OLM has not installed ..." | OLM could not resolve the subscription, often because of a dependency on another operator. The message quotes OLM's reason |
| "demo_images.postgresql is ... Pin it to a tag" | Set the tag as described at the start of step 6 |
| PostgreSQL never becomes ready | `oc get pods -n aiops-data` and `oc logs deployment/postgres -n aiops-data`. An image pull error usually means the tag does not exist |
| "The database setup job did not succeed" | `oc logs job/postgres-setup -n aiops-data` shows psql's error |
| "The MaaS gateway is not programmed" | `oc describe gateway maas-default-gateway -n openshift-ingress`. The gateway controller may still be deploying its proxy; rerun after a few minutes |
| "Models-as-a-Service is not ready" | The message quotes the DataScienceCluster condition. A database error usually means `maas-db-config` was missing when MaaS started: rerun, then `oc rollout restart deployment/maas-api` in the namespace the message names |
| "The MLflow server is not ready" | The message quotes the MLflow resource's status. Check the migration Job's log as the message shows: `SSL error: certificate verify failed` means MLflow does not have the service CA bundle; check that `mlflow-postgres-ca` in `redhat-ods-applications` has a `service-ca.crt` key |
| "The model ... is not ready" | The message quotes the LLMInferenceService's conditions. `oc get pods -n aiops-models`, then `oc describe pod` for pull or scheduling errors and `oc logs` on the pod's `main` container for vLLM errors. `CUDA out of memory` means the model and context length do not fit the L4: lower `max_model_len` in `demo_model`. `Insufficient nvidia.com/gpu` means something else holds the GPU: rerun phase 01 |
| "MaaS has not accepted ..." | The message quotes the MaaSModelRef's status. "Awaiting governance pairing" means MaaS does not see an active policy and subscription that both name the model: check that they reference `aiops-models` and the model name. "Backend" errors mean the model or its gateway reference is wrong |
| "The MaaSAuthPolicy (or MaaSSubscription) for the enrichment service is ..." | The message quotes the resource's status. A model that is "not found" usually means the MaaSModelRef is not ready yet: rerun |
| "Cannot reach the MaaS gateway" (when checking or minting the key) | The `maas.` name does not resolve yet, or the gateway is not programmed. `oc get gateway -n openshift-ingress`, wait a few minutes for DNS, and rerun |
| "MaaS refused to mint the key" | The message quotes MaaS's status and error. A 401 or 403 means MaaS did not accept the service account token; a 400 often names a subscription that is missing or not active |
| "MaaS does not offer ... to the enrichment service's key" | The message lists the models MaaS offers the key. Check that the subscription names the model and its namespace |
| "Access checks (HTTP status): ..." | The message lists each check's status. 404 for every check, including the one with no key, means the gateway found no route for the request: the model ID in the Secret is not one MaaS publishes; a 429 means the token budget is used up for this hour; a 200 with no key means the gateway is not enforcing keys; a revoked key that still gets 200 means the revocation wait was too short, so rerun |
| "The platform is not ready" (phase 03) | The message lists the platform's conditions. `oc get ansibleautomationplatform aap -n aap -o yaml` shows the operator's detail and `oc get pods -n aap` which component is not running |
| Incidents stop being raised, and the *Monitoring integration* or *AI incident enrichment trigger* activation log shows "License has expired" | The AAP subscription in the manifest has expired, so AAP refuses to launch any job. Export a fresh manifest from the Customer Portal's subscription allocations, load it with the `aap_manifest_b64` line in laptop setup step 3, and rerun phase 03, which replaces an expired subscription. Phase 03 warns when the subscription has less than a week left |
| "The platform did not accept the manifest" (phase 03) | The message quotes the platform's reason. Check that `aap_manifest_b64` holds the manifest .zip from the Customer Portal, base64-encoded as in laptop setup, and that its allocation has not expired. Download a fresh manifest and repeat the laptop setup line if needed |
| "Kuadrant is not ready" | Check the message, then `oc get kuadrant kuadrant -n kuadrant-system -o yaml` and the pods in `kuadrant-system` |
| Monitoring wait times out | Check `oc get pods -n openshift-user-workload-monitoring` and `oc get co monitoring` |
