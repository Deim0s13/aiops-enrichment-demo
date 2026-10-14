# Build roles

Roles used by the build phases in `playbooks/`.

| Role | Used by | Purpose |
|---|---|---|
| `vault_bootstrap` | `00_secrets.yml` | Runs Vault on the operator's laptop and configures its KV engine, policies and AppRoles |
| `secrets` | Every phase that needs a secret | The only place that reads secrets: resolves the names in `demo_required_secrets` from Vault or the local file, depending on `demo_secrets_backend`. Refuses to run at `-vvv` and above. When it reads the cluster group, it checks that the API is reachable and accepts the token before the phase changes anything |
| `olm_operator` | Phases that need an operator | Installs one operator through OLM (namespace, OperatorGroup, Subscription, then waits for the CSV), or adopts it if it is already installed. Checks the channel exists in the catalogue first, and enforces a minimum version. Records what it found in `olm_operator_results` |
| `postgres` | `02_openshift_ai.yml` (and phase 06) | The shared PostgreSQL: TLS from the service CA, generated passwords kept in the cluster, and a database and user per entry in `postgres_databases`, created by an idempotent Job. Publishes `postgres_connection` (host, port and credentials Secret) for its clients |
| `openshift_ai` | `02_openshift_ai.yml` | The platform team's part: checks OpenShift AI, installs Red Hat Connectivity Link, creates the Kuadrant instance and the MaaS gateway, switches on Models-as-a-Service and MLflow, and runs the MLflow server |
| `model_serving` | `02_openshift_ai.yml` (and the model test, M1.6) | The model owner's part: serves one model on vLLM as an `LLMInferenceService` behind the MaaS gateway and registers it with MaaS |
| `maas_consumer` | `02_openshift_ai.yml` | The application team's part: onboards one consumer to one model, with its own service account, a policy, a token budget and an API key that belongs to it, stored with the model's ID and URL in one Secret. Then checks access through the gateway |
| `platform` | `01_platform.yml` | Frees the GPU, checks the GPU stack and default storage the environment provides, and enables user workload monitoring with its Alertmanager. Installs no operators (DD13) |

## Conventions

- **Inputs, not kit settings.** Each role takes role-prefixed inputs, and the playbook fills them from the kit's `demo_*` settings in `inventory/group_vars/all/main.yml`. The roles do not read `demo_*` themselves, so each can be called on its own, for example `model_serving` once per candidate model in the model test. The `secrets` and `vault_bootstrap` roles are the exception: they exist to serve the kit's settings.
- **Required inputs are declared** in each role's `meta/argument_specs.yml`, so a missing or misspelt input stops the play before the role changes anything.
- **Roles find what they need on the cluster.** `maas_consumer` reads the MaaS address from the gateway rather than from `openshift_ai`, as an application team would.
- **Cluster access** comes from the `module_defaults` the calling play sets.
