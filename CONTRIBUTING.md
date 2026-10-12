# Contributing

## Ground rules

- **Ansible only for deployment and configuration.** Every change to the environment is made by a playbook, so the kit can be rebuilt from an empty cluster. Shell scripts are not used for build steps. Application code in `services/` is the exception.
- **Idempotent and rerunnable.** Every phase must be safe to run twice, and must not depend on state left behind by a previous environment.
- **No secrets, ever.** Read [SECURITY.md](SECURITY.md) before your first commit.
- **Fictional data only.** No customer names, data or material.
- **Traceable to the design.** Changes that alter the architecture update [docs/implementation-design.md](docs/implementation-design.md) in the same pull request.

## Setup

```bash
pre-commit install
pre-commit run --all-files
```

## Conventions

- Use fully qualified collection names (`ansible.builtin.copy`, not `copy`).
- When a playbook or role starts using a module from a collection other than `ansible.builtin`, add it to `mock_modules` in `.ansible-lint`. Linting runs offline, without collections installed, so it cannot otherwise resolve the module.
- Name every play and task.
- Tag each phase with its phase name, so `site.yml --tags <phase>` works.
- Use British English in documentation.
- Pin collection and image versions once a phase has been built successfully.
- Source container images in the order set by DD12 in the implementation design: Red Hat Hardened Images where viable, then UBI-based images, then other sources only where neither exists, with the reason recorded.
