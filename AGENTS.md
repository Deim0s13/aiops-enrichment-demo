# Instructions for AI coding assistants

This repository builds a demonstration of AI-assisted incident enrichment on OpenShift AI and Ansible Automation Platform. Read `docs/implementation-design.md` before making changes. It is the source of truth for components, interfaces, identities and scope.

## Rules

- Deployment and configuration are written as Ansible playbooks and roles only. Do not add shell scripts or Makefiles for build steps.
- Never write a secret, token, password, key, certificate or pull secret into any file, including examples and tests. Use the lookups described in `SECURITY.md`.
- Set `no_log: true` on every task that handles a secret.
- Use fully qualified collection names and name every play and task. Code must pass `pre-commit run --all-files`.
- Use fictional organisation and service names only.
- Keep `playbooks/` (build phases, run from a laptop) separate from `automation/` and `rulebooks/` (content AAP runs).
- Documentation uses British English and does not use em dashes.
- If a change departs from the implementation design, update the design in the same change and say why.
