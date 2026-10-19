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
- Build roles take their settings as role-prefixed inputs, which the playbook fills from the kit's `demo_*` settings; roles do not read `demo_*` themselves. Declare required inputs in `meta/argument_specs.yml`. A role that another role or play needs to call on its own finds what it needs on the cluster rather than relying on facts from another role. The exceptions are the cluster credentials, which come from `module_defaults` or, for `uri` calls to the cluster API, from the `secrets` role's `secrets_values` and `secrets_cluster_ca_file`, and the `secrets` and `vault_bootstrap` roles, which exist to serve the kit's settings. Any other secret a role needs is read from `secrets_values` inside the role, never passed in as a role input, so it is not printed with the role's arguments.
- Give every single-shot `kubernetes.core.k8s_info` read `until: RESULT is not failed`, `retries: 3` and `delay: 5`: the single-node API server occasionally drops a connection. Waits already retry. Do not retry writes, so a failed change stops the build visibly.
- Do not use `kubernetes.core.k8s_exec`: in `kubernetes.core` 6.6.0 it fails to import with current Kubernetes Python clients. Run one-off work in a cluster as a Job instead.
- Add any new non-builtin module to `mock_modules` in `.ansible-lint`, and lint in an environment without collections installed, as pre-commit and CI do.
- Prove controls by trying to break them, not by reading their configuration. Each phase ends with checks that act as the identity concerned and read the outcome back from the system of record (ServiceNow, the cluster), rather than trusting the response of the call. Test data the checks create is labelled with a fixed prefix and removed at the end.
- Configure ServiceNow through the `servicenow` role's `record.yml`: find the record, create it if missing, change only the fields that differ. The `servicenow.itsm.api` module itself always creates on post and always reports a change on patch. Values ServiceNow returns as strings are written as strings ("true", "10").
- Ansible does not template the keys of a literal mapping. Build a mapping whose key comes from a variable as an expression, for example `headers: "{{ {header_name: value} }}"`.
- In Jinja, read a field called `items`, `keys` or `values` with `['items']`, not `.items`, which is the dictionary's method.
- Do not name a file `secrets.yml` or `secrets.*.yml` anywhere: `.gitignore` ignores those names so a real secrets file cannot be committed, and the file silently drops out of the commit.
- Playbooks that run on the laptop with `ansible-playbook` (`00_secrets.yml`, `07_execution_environment.yml`) need the laptop collections in `collections/requirements-laptop.yml` and `hvac`; everything else runs in the execution environment. The cluster node is x86_64, so anything the cluster runs is built for linux/amd64.
- Use fictional organisation and service names only: the organisation is ACME Bank.
- Keep `playbooks/` (build phases, run from a laptop) and `evaluation/` (tests run from a laptop, not part of the build) separate from `automation/` and `rulebooks/` (content AAP runs).
- Documentation uses British English and does not use em dashes.
- If a change departs from the implementation design, update the design in the same change and say why.
