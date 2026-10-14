# Build roles

Roles used by the build phases in `playbooks/`.

| Role | Used by | Purpose |
|---|---|---|
| `vault_bootstrap` | `00_secrets.yml` | Runs Vault on the operator's laptop and configures its KV engine, policies and AppRoles |
| `secrets` | Every phase that needs a secret | The only place that reads secrets: resolves the names in `demo_required_secrets` from Vault or the local file, depending on `demo_secrets_backend`. Refuses to run at `-vvv` and above |
| `olm_operator` | Phases that need an operator | Installs one operator through OLM (namespace, OperatorGroup, Subscription, then waits for the CSV), or adopts it if it is already installed. Checks the channel exists in the catalogue first, and enforces a minimum version. Records what it found in `olm_operator_results` |
| `openshift_ai` | `02_openshift_ai.yml` | Checks OpenShift AI, installs Red Hat Connectivity Link, creates the Kuadrant instance and the MaaS gateway, switches on Models-as-a-Service and MLflow, serves the model in `demo_model` and publishes it to MaaS, gives the enrichment service's service account a policy, a subscription and an API key (kept in the `maas-api-key` Secret), and checks access through the gateway |
| `postgres` | `02_openshift_ai.yml` (and phase 06) | The shared PostgreSQL: TLS from the service CA, generated passwords kept in the cluster, and a database and user per entry in `demo_postgres_databases`, created by an idempotent Job |
| `platform` | `01_platform.yml` | Frees the GPU, checks the GPU stack and default storage the environment provides, and enables user workload monitoring with its Alertmanager. Installs no operators (DD13) |
