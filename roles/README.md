# Build roles

Roles used by the build phases in `playbooks/`.

| Role | Used by | Purpose |
|---|---|---|
| `vault_bootstrap` | `00_secrets.yml` | Runs Vault on the operator's laptop and configures its KV engine, policies and AppRoles |
| `secrets` | Every phase that needs a secret | The only place that reads secrets: resolves the names in `demo_required_secrets` from Vault or the local file, depending on `demo_secrets_backend`. Refuses to run at `-vvv` and above |
| `platform` | `01_platform.yml` | Frees the GPU, checks the GPU stack and default storage the environment provides, and enables user workload monitoring with its Alertmanager. Installs no operators (DD13) |
