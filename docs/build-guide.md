# Build guide

This guide builds the demo on a demo environment, one phase at a time. Follow it for every new environment. It assumes [laptop-setup.md](laptop-setup.md) is complete: Vault holds your entitlements and ServiceNow credentials, the execution environment is built, and preflight passes with the cluster checks skipped.

Sections are added as each phase is implemented. Phases 02 onwards are not implemented yet.

| Step | What you end up with | Time |
|---|---|---|
| 1 | A demo environment | Provisioning time |
| 2 | Vault unsealed, with AppRole credentials for this environment | 2 minutes |
| 3 | The cluster's API URL, CA certificate and token in Vault | 2 minutes |
| 4 | Preflight passing, including the cluster | 1 minute |
| 5 | Phase 01: GPU freed, GPU stack checked, user workload monitoring enabled | 5 minutes, up to 25 on a fresh environment |

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

The token is an OpenShift session token and expires after 24 hours by default. If preflight later reports that the cluster did not accept the token, log in again and repeat the `api_token` line.

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

## Finish your session

Stop Vault. Your secrets stay encrypted on its volume:

```bash
podman stop aiops-demo-vault
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "This run uses verbosity 3" | Secrets are not read at `-vvv` and above. Use `-vv` |
| Preflight: "did not accept the token" | The session token expired. Log in again and repeat the `api_token` line in step 3 |
| "The API presents a certificate signed by a CA that is not publicly trusted" | The CA bundle is not in Vault. Load it with the `api_ca_cert` line in step 3 |
| "The API certificate is not signed by the CA bundle" | The bundle in Vault belongs to an earlier environment. Repeat the `api_ca_cert` line in step 3. As a last resort, `-e demo_cluster_validate_certs=false` turns verification off, which sends the token to a server that has not been verified |
| "Pods in ... hold the GPU" | A workload other than the RHDP sample holds the GPU. List its pods with `oc get pods -n` followed by the namespace in the message, and stop or delete it. If it is a sample that every environment ships, add its namespace to `demo_gpu_reclaimable_namespaces` in `inventory/group_vars/all/main.yml` |
| "Expected Node Feature Discovery and the NVIDIA GPU Operator to be installed" | The environment does not provide the GPU stack. Check that you ordered the RHDP OpenShift AI catalogue item. Phase 01 does not install operators (DD13) |
| "The NVIDIA ClusterPolicy is not ready" | The driver is still compiling, or failed. Rerun in a few minutes. If it persists, check `oc get pods -n nvidia-gpu-operator` |
| Monitoring wait times out | Check `oc get pods -n openshift-user-workload-monitoring` and `oc get co monitoring` |
