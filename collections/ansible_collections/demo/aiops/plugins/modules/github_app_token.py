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

import base64
import json
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt(app_id, private_key):
    """An RS256 JSON Web Token for the App, valid for nine minutes (GitHub allows ten)."""
    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    signature = key.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{_b64(signature)}"


def call(module, method, url, token, body=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "acme-knowledge-bot"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body)
    response, info = fetch_url(module, url, data=data, headers=headers, method=method, timeout=30)
    content = response.read() if response else info.get("body", b"")
    try:
        parsed = json.loads(content or b"{}")
    except ValueError:
        parsed = {}
    return info.get("status", -1), parsed


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
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg="The cryptography Python package is needed to sign the App's token.")
    params = module.params
    if params["repository"].count("/") != 1:
        module.fail_json(msg=f"repository should be owner/name, not {params['repository']!r}.")
    api = params["api_url"].rstrip("/")
    try:
        signed = app_jwt(params["app_id"], params["private_key"])
    except (ValueError, TypeError) as error:
        module.fail_json(msg=f"The App's private key could not be read: {type(error).__name__}. Check github_app_private_key in Vault.")

    status, found = call(module, "GET", f"{api}/repos/{params['repository']}/installation", signed)
    if status != 200:
        module.fail_json(msg=f"GitHub did not find the App installed on {params['repository']} (HTTP {status}: "
                             f"{found.get('message', 'no message')}). Check the App ID and that the App is installed on it.")
    installation = found["id"]
    status, granted = call(module, "POST", f"{api}/app/installations/{installation}/access_tokens", signed,
                           {"repositories": [params["repository"].split("/")[1]], "permissions": params["permissions"]})
    if status != 201 or not granted.get("token"):
        module.fail_json(msg=f"GitHub refused an installation token (HTTP {status}: {granted.get('message', 'no message')}). "
                             "Check that the App has the permissions asked for.")
    module.exit_json(changed=False, token=granted["token"], expires_at=granted.get("expires_at", ""),
                     installation_id=installation)


if __name__ == "__main__":
    main()
