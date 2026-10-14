# Instructions for AI coding assistants

This repository builds a demonstration of AI-assisted incident enrichment on OpenShift AI and Ansible Automation Platform. Read `docs/implementation-design.md` before making changes. It is the source of truth for components, interfaces, identities and scope.

## Rules

- Deployment and configuration are written as Ansible playbooks and roles only. Do not add shell scripts or Makefiles for build steps.
- Never write a secret, token, password, key, certificate or pull secret into any file, including examples and tests. Use the lookups described in `SECURITY.md`.
- Set `no_log: true` on every task that handles a secret. Never reference `secrets_values` in a `debug` task; a pre-commit hook blocks it.
- Never rely on a module to mask secrets in its own output. Check new secret-handling tasks at `-vvv`, with throwaway values and `secrets_allow_debug_verbosity=true`.
- Kubernetes tasks get the cluster token through `module_defaults`, not task arguments, and do not need `no_log`: the `secrets` role refuses to run at `-vvv`, where `kubernetes.core` prints the token. List `kubernetes.core` modules individually in `module_defaults`, because lint cannot resolve the action group without collections installed.
- Use fully qualified collection names and name every play and task. Code must pass `pre-commit run --all-files`.
- Do not loop a later task over the registered results of a Kubernetes task: each item carries the module invocation, cluster token included, which is printed at `-vv`. Reduce the results to the fields you need in a `set_fact` with `no_log`, then loop over that.
- Do not use `kubernetes.core.k8s_exec`: in `kubernetes.core` 6.6.0 it fails to import with current Kubernetes Python clients. Run one-off work in a cluster as a Job instead.
- Add any new non-builtin module to `mock_modules` in `.ansible-lint`, and lint in an environment without collections installed, as pre-commit and CI do.
- Use fictional organisation and service names only: the organisation is ACME Bank.
- Keep `playbooks/` (build phases, run from a laptop) separate from `automation/` and `rulebooks/` (content AAP runs).
- Documentation uses British English and does not use em dashes.
- If a change departs from the implementation design, update the design in the same change and say why.
