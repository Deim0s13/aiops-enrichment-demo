# Build roles

Roles used by the build phases in `playbooks/`. The planned `secrets` role is the only place that reads secrets: it resolves the names in `demo_required_secrets` from Vault or the local file, depending on `demo_secrets_backend`.
