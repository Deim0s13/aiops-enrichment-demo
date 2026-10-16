# Build guide

This guide builds the demo on a demo environment, one phase at a time. Follow it for every new environment. It assumes [laptop-setup.md](laptop-setup.md) is complete: Vault holds your entitlements and ServiceNow credentials, the execution environment is built, and preflight passes with the cluster checks skipped.

Sections are added as each phase is implemented. Phases 01 to 03 are implemented. Phases 04 onwards are not implemented yet.

| Step | What you end up with | Time |
|---|---|---|
| 1 | A demo environment | Provisioning time |
| 2 | Vault unsealed, with AppRole credentials for this environment | 2 minutes |
| 3 | The cluster's API URL, CA certificate and token in Vault | 2 minutes |
| 4 | Preflight passing, including the cluster | 1 minute |
| 5 | Phase 01: GPU freed, GPU stack checked, user workload monitoring enabled | 5 minutes, up to 25 on a fresh environment |
| 6 | Phase 02: OpenShift AI checked, Connectivity Link installed, PostgreSQL deployed, Models-as-a-Service and MLflow enabled, the model served and published, the enrichment service given governed access, and the access checks passed | About 15 minutes, plus up to 30 for the first model start |
| 7 | Phase 03: AAP operator installed, the platform running with Controller and Event-Driven Ansible, and its subscription attached | About 20 minutes on the first run |

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

10. **Gives the enrichment service governed access.** The service gets its own identity, the `aiops-enrichment` service account in `aiops-enrichment`. A `MaaSAuthPolicy` allows that identity to call the model and a `MaaSSubscription` gives it a token budget (100,000 tokens an hour, set in `demo_maas_consumer`). Both are in `models-as-a-service`. Once both are active, MaaS accepts the model and routes requests for it.
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

## Finish your session

Stop Vault. Your secrets stay encrypted on its volume:

```bash
podman stop aiops-demo-vault
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "This run uses verbosity 3" | Secrets are not read at `-vvv` and above. Use `-vv` |
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
| "The platform did not accept the manifest" (phase 03) | The message quotes the platform's reason. Check that `aap_manifest_b64` holds the manifest .zip from the Customer Portal, base64-encoded as in laptop setup, and that its allocation has not expired. Download a fresh manifest and repeat the laptop setup line if needed |
| "Kuadrant is not ready" | Check the message, then `oc get kuadrant kuadrant -n kuadrant-system -o yaml` and the pods in `kuadrant-system` |
| Monitoring wait times out | Check `oc get pods -n openshift-user-workload-monitoring` and `oc get co monitoring` |
