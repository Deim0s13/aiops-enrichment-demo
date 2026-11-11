#!/usr/bin/python
"""Short-lived GitHub token for a GitHub App installation (DD33)."""

DOCUMENTATION = r"""
module: github_app_token
short_description: Get a short-lived installation token for a GitHub App, for one repository
description:
  - Signs a JSON Web Token as the GitHub App with its private key, finds the App's installation on the
    repository, and asks GitHub for an installation token limited to that repository and the permissions
    given. The token expires within an hour; the private key never leaves the job.
  - Used by the knowledge bot, acme-knowledge-bot, to open pull requests (DD33).
options:
  app_id:
    description: The GitHub App's ID.
    type: str
    required: true
  private_key:
    description: The App's private key, in PEM format.
    type: str
    required: true
  repository:
    description: The repository, as owner/name.
    type: str
    required: true
  permissions:
    description: The permissions the token may use, each no wider than the App's own.
    type: dict
    default: {contents: write, pull_requests: write}
  api_url:
    description: The GitHub API's address.
    type: str
    default: https://api.github.com
  validate_certs:
    description: Check the API's certificate.
    type: bool
    default: true
author: aiops-enrichment-demo
"""

RETURN = r"""
token:
  description: The installation token. Keep the task under no_log.
  type: str
  returned: success
expires_at:
  description: When the token expires.
  type: str
  returned: success
installation_id:
  description: The App's installation on the repository.
  type: int
  returned: success
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.demo.aiops.plugins.module_utils.github_app import call, signed


def main():
    module = AnsibleModule(
        argument_spec={
            "app_id": {"type": "str", "required": True},
            "private_key": {"type": "str", "required": True, "no_log": True},
            "repository": {"type": "str", "required": True},
            "permissions": {"type": "dict", "default": {"contents": "write", "pull_requests": "write"}},
            "api_url": {"type": "str", "default": "https://api.github.com"},
            "validate_certs": {"type": "bool", "default": True},
        },
        supports_check_mode=True,
    )
    params = module.params
    if params["repository"].count("/") != 1:
        module.fail_json(msg=f"repository should be owner/name, not {params['repository']!r}.")
    api = params["api_url"].rstrip("/")
    token = signed(module, params["app_id"], params["private_key"])

    status, found = call(module, "GET", f"{api}/repos/{params['repository']}/installation", token)
    if status != 200:
        module.fail_json(msg=f"GitHub did not find the App installed on {params['repository']} (HTTP {status}: "
                             f"{found.get('message', 'no message')}). Check the App ID and that the App is installed on it.")
    installation = found["id"]
    status, granted = call(module, "POST", f"{api}/app/installations/{installation}/access_tokens", token,
                           {"repositories": [params["repository"].split("/")[1]], "permissions": params["permissions"]})
    if status != 201 or not granted.get("token"):
        module.fail_json(msg=f"GitHub refused an installation token (HTTP {status}: {granted.get('message', 'no message')}). "
                             "Check that the App has the permissions asked for.")
    module.exit_json(changed=False, token=granted["token"], expires_at=granted.get("expires_at", ""),
                     installation_id=installation)


if __name__ == "__main__":
    main()
