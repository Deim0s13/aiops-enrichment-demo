# Laptop setup

This guide covers milestone M0: everything on the operator's laptop that must be in place before a demo environment is requested. It is written for macOS with Podman. Linux differences are noted where they matter.

At the end, `00_preflight.yml` passes against your own Vault with the cluster checks skipped.

| Step | What you end up with | Plan task |
|---|---|---|
| 1 | Tools installed and a Podman machine running | M0.4 |
| 2 | Vault running, initialised and configured | M0.5 |
| 3 | Your entitlements and ServiceNow credentials in Vault | M0.1 to M0.3 |
| 4 | The execution environment built | M0.7 |
| 5 | Preflight passing | M0.6 |

## Before you start

Gather these. Each is your own and is never shared.

- **OpenShift pull secret** from console.redhat.com, under OpenShift > Downloads, saved as a file.
- **AAP subscription manifest** (a .zip) from the Red Hat Customer Portal subscription allocations page, allocated to a subscription you are entitled to use for demos.
- **Automation Hub offline token** from console.redhat.com, under Ansible Automation Platform > Automation Hub > Connect to Hub. Offline tokens expire after 30 days without use.
- **registry.redhat.io credentials.** A registry service account from access.redhat.com/terms-based-registry is better than your personal login, because it can be revoked on its own.
- **ServiceNow PDI** from developer.servicenow.com: the instance URL and the admin password.

## 1 Install the tools

Skip anything you already have.

```bash
brew install podman
podman machine init --cpus 4 --memory 8192    # only if you have no machine yet
podman machine start

# Red Hat registries: execution environment base image and the UBI-based Vault image.
# Use your registry service account for both.
podman login registry.redhat.io
podman login registry.connect.redhat.com

# ansible-core does not yet support Python 3.15, Homebrew's current python3, so pin 3.14
brew install python@3.14
python3.14 -m venv ~/.venvs/aiops-demo
source ~/.venvs/aiops-demo/bin/activate
pip install ansible-core ansible-navigator ansible-builder pre-commit

cd ~/Projects/aiops-enrichment-demo
ansible-galaxy collection install -r collections/requirements-laptop.yml
pre-commit install
```

## 2 Start Vault

`00_secrets.yml` runs Vault Community Edition, using HashiCorp's UBI-based image from Red Hat's partner registry, in a Podman container, with storage on a persistent volume and the API published on `127.0.0.1:8200` only. It runs directly with `ansible-playbook`, not inside the execution environment, because it manages a container on your laptop.

```bash
ansible-playbook playbooks/00_secrets.yml
```

The first run initialises Vault and writes two files to `~/.config/aiops-demo/`, both readable only by you:

| File | Contents | What to do |
|---|---|---|
| `vault-init.json` | Unseal key and root token | Copy both into your password manager, then delete the file |
| `approle.env` | Read-only AppRole credentials for the build, one per secret group | Keep it. Run `source ~/.config/aiops-demo/approle.env` before using `ansible-navigator` |

```bash
cat ~/.config/aiops-demo/vault-init.json    # copy into your password manager
rm ~/.config/aiops-demo/vault-init.json
```

The Vault UI is at http://127.0.0.1:8200/ui if you prefer it to the commands below.

## 3 Load your secrets

Secrets are entered through the `vault` CLI inside the container, reading values from standard input, so they never appear on a command line or in your shell history. Paste each command exactly as written. A command that starts with `read -rs` then waits silently for one secret: paste it there and press Enter. The secret never goes into the command itself, and `-` in `key=-` stays, because it tells Vault to read the value from that input. Set the root token for this session only:

```bash
read -rs VAULT_TOKEN && export VAULT_TOKEN            # paste the root token, then Enter
v() { podman exec -i -e VAULT_TOKEN aiops-demo-vault vault "$@"; }
```

**Entitlements.** The first command creates the secret; the rest add keys to it with `patch`.

```bash
v kv put   -mount=aiops-demo entitlements pull_secret=- < ~/Downloads/pull-secret.txt
base64 -i ~/Downloads/manifest_*.zip | v kv patch -mount=aiops-demo entitlements aap_manifest_b64=-
read -rs T && printf %s "$T" | v kv patch -mount=aiops-demo entitlements automation_hub_token=- ; unset T
v kv patch -mount=aiops-demo entitlements registry_username='<registry service account username>'
read -rs T && printf %s "$T" | v kv patch -mount=aiops-demo entitlements registry_password=- ; unset T
```

**ServiceNow.**

```bash
v kv put -mount=aiops-demo servicenow instance_url=https://devNNNNNN.service-now.com admin_username=admin
read -rs T && printf %s "$T" | v kv patch -mount=aiops-demo servicenow admin_password=- ; unset T
```

**Source.** AAP syncs this repository as its project, and the repository is private, so AAP needs a token that can read it and nothing else (DD16). In GitHub, open Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token, and set:

- Token name `aiops-demo-aap`, with an expiry that covers your demo period (90 days, say)
- Resource owner: your account; Repository access: Only select repositories, `aiops-enrichment-demo`
- Repository permissions: Contents, Read-only. GitHub adds Metadata, Read-only, by itself. Nothing else

Copy the token (it starts `github_pat_`), then store it:

```bash
read -rs T && printf %s "$T" | v kv put -mount=aiops-demo source github_token=- ; unset T
```

Preflight checks that the token can read the repository, and tries a harmless write (a branch pointing at a commit that does not exist) to confirm it is refused. GitHub reports what your account may do on the repository, not what the token may do, so trying is the only reliable test. When it expires, create a new one and store it the same way.

**Cluster.** Skip this for now. The cluster secrets change with every demo environment, so they are loaded as part of each build: see step 3 of [build-guide.md](build-guide.md).

Check what is stored without showing values, then drop the root token from your session:

```bash
keys() { v kv get -mount=aiops-demo -format=json "$1" | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin)["data"]["data"]))'; }
keys entitlements; keys servicenow; keys source
unset VAULT_TOKEN
```

Once the downloads are in Vault, delete the pull secret and manifest from `~/Downloads`.

## 4 Build the execution environment

The build pulls the AAP 2.7 minimal execution environment image and installs certified collections from Automation Hub. It uses the registry login from step 1.

The Automation Hub token reaches the build as a build argument named on the command line **without a value**. Podman then reads the value from your environment. This matters: `ansible-builder` prints the full `podman build` command before running it, so a token passed as `NAME=value` would appear in your terminal. The token is declared only in the collection download stage, which is not part of the final image.

Run these one line at a time:

```bash
read -rs VAULT_TOKEN && export VAULT_TOKEN
export ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN=$(v kv get -mount=aiops-demo -field=automation_hub_token entitlements)
unset VAULT_TOKEN; echo ${#ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN}
```

The last line prints the token's length, not the token: expect several hundred characters. If it prints `0`, stop and check Vault.

```bash
ansible-builder build -f execution-environment/execution-environment.yml -t localhost/aiops-demo-ee:latest --build-arg ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN
```

Then remove the token from your session and the intermediate build images, which can record build argument values in their history:

```bash
unset ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN
podman image prune -f
```

Never pass the token as `--build-arg ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN="$ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN"`. That form puts the value in the printed command.

This image runs on your laptop, so on Apple silicon it is built for arm64. AAP in the cluster will need an amd64 image, which is handled in milestone M2.

Once it builds, record the collection versions it resolved and pin them in `collections/requirements.yml`:

```bash
podman run --rm localhost/aiops-demo-ee:latest ansible-galaxy collection list
```

## 5 Run preflight

```bash
source ~/.config/aiops-demo/approle.env
ansible-navigator run playbooks/00_preflight.yml -e preflight_include_cluster=false
```

Preflight logs in to Vault with each group's AppRole in turn and reads that group's secrets. It checks that each secret is set and in the right format, then checks that the credentials actually work: registry.redhat.io accepts your registry service account, Red Hat single sign-on accepts your Automation Hub token, and the ServiceNow PDI is awake and accepts the admin password. It revokes each Vault token once the group is read and reports secrets by name only, never by value. Exchanging the Automation Hub token also counts as using it, which resets its 30-day expiry.

Once you have a demo environment and have loaded the cluster secrets, run it without `-e preflight_include_cluster=false`. It then also checks that the cluster API is reachable and accepts the token, and reports the OpenShift version and instance type.

## Day to day

**When you finish a session**, stop Vault. Your secrets stay encrypted on the volume:

```bash
podman stop aiops-demo-vault
```

**To start it again**, or after a laptop restart, run the playbook with your unseal key. It starts the container and unseals Vault, which always starts sealed:

```bash
podman machine start
read -rs AIOPS_VAULT_UNSEAL_KEY && export AIOPS_VAULT_UNSEAL_KEY
ansible-playbook playbooks/00_secrets.yml
unset AIOPS_VAULT_UNSEAL_KEY
```

**For each new demo environment**, issue new AppRole secret IDs at the same time as you load the new cluster token. Secret IDs expire after 7 days, and issuing new ones revokes the previous ones:

```bash
read -rs VAULT_TOKEN && export VAULT_TOKEN
ansible-playbook playbooks/00_secrets.yml -e vault_bootstrap_rotate_secret_id=true
unset VAULT_TOKEN
source ~/.config/aiops-demo/approle.env
```

Then load the cluster secrets and rerun preflight, as described in [build-guide.md](build-guide.md).

Issuing new secret IDs also creates the AppRole and read policy for any secret group added since Vault was set up, such as `source`, so a new group needs no other step once its secret is stored.

## Without Vault

The tested path is Vault. If you cannot run it, the local backend reads an encrypted file instead:

```bash
mkdir -p ~/.config/aiops-demo/local
cp secrets.example.yml ~/.config/aiops-demo/local/secrets.yml
# edit the file, then:
ansible-vault encrypt ~/.config/aiops-demo/local/secrets.yml

ansible-navigator run playbooks/00_preflight.yml \
  -e demo_secrets_backend=local -e preflight_include_cluster=false \
  --eev ~/.config/aiops-demo/local:/runner/aiops-secrets:Z \
  --pae false --ask-vault-pass
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `AttributeError: module 'dataclasses' has no attribute '_is_type'` | The virtual environment uses a Python that ansible-core does not support yet, usually after Homebrew upgrades `python3`. Recreate it with Python 3.14, as in step 1 |
| "This run uses verbosity 3" | Secrets are not resolved at `-vvv` and above, because some modules print credentials at that verbosity (see SECURITY.md). Use `-vv` |
| Preflight: "Cannot reach Vault at http://host.containers.internal:8200" | The Vault container is not running (`podman ps`), or the Podman machine is stopped. On Linux, `host.containers.internal` may not reach a port bound to `127.0.0.1`: set `AIOPS_VAULT_ADDR=http://127.0.0.1:8200` and add `--execution-environment-container-options="--net=host"` |
| "Vault is sealed" | The laptop or Podman machine restarted. Unseal as above |
| "Vault refused the ... AppRole login" or "approle.env has no credentials for ..." | The secret IDs expired or were rotated, or `approle.env` was not sourced in this terminal. Issue new ones as above |
| "The ServiceNow PDI looks like it is hibernating" | Wake it at developer.servicenow.com. PDIs hibernate after a period without use and are reclaimed if left long enough |
| "ServiceNow did not accept the administrator credentials" | The PDI password changes when an instance is reclaimed or upgraded. Update `aiops-demo/servicenow` |
| "The API presents a certificate signed by a CA that is not publicly trusted" | Load the cluster's CA bundle, as in step 3 of [build-guide.md](build-guide.md) |
| "registry.redhat.io rejected registry_username and registry_password" | The registry service account was deleted or its token regenerated. Check it at access.redhat.com/terms-based-registry and update `aiops-demo/entitlements` |
| "Red Hat single sign-on rejected automation_hub_token" | The offline token expired after 30 days without use. Generate a new one and update it in Vault |
| Execution environment build fails to download collections | The Automation Hub token has expired. Run preflight to confirm, then generate a new one and update it in Vault |
