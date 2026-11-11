#!/usr/bin/python
"""Points a GitHub App's webhook at an address, with a shared secret (DD34)."""

DOCUMENTATION = r"""
module: github_app_webhook
short_description: Set where a GitHub App sends its webhook events, and the secret it signs them with
description:
  - Signs as the GitHub App and sets its webhook's address, content type and secret, so the App's events reach
    an EDA event stream whose address changes with every demo environment (DD34).
  - Reports whether the App is subscribed to push events and whether its webhook is active. Both are App
    settings that only the App's owner can change, on GitHub.
options:
  app_id:
    description: The GitHub App's ID.
    type: str
    required: true
  private_key:
    description: The App's private key, in PEM format.
    type: str
    required: true
  url:
    description: Where GitHub should deliver the App's events.
    type: str
    required: true
  secret:
    description: The secret GitHub signs each delivery with (X-Hub-Signature-256).
    type: str
    required: true
  insecure_ssl:
    description: Whether GitHub may deliver without checking the address's certificate. Leave off unless the route's certificate is not publicly trusted.
    type: bool
    default: false
  api_url:
    description: The GitHub API's address.
    type: str
    default: https://api.github.com
author: aiops-enrichment-demo
"""

RETURN = r"""
url:
  description: The address the webhook now delivers to.
  type: str
  returned: success
events:
  description: The events the App is subscribed to.
  type: list
  returned: success
push_subscribed:
  description: Whether the App is subscribed to push events.
  type: bool
  returned: success
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.demo.aiops.plugins.module_utils.github_app import call, signed


def main():
    module = AnsibleModule(
        argument_spec={
            "app_id": {"type": "str", "required": True},
            "private_key": {"type": "str", "required": True, "no_log": True},
            "url": {"type": "str", "required": True},
            "secret": {"type": "str", "required": True, "no_log": True},
            "insecure_ssl": {"type": "bool", "default": False},
            "api_url": {"type": "str", "default": "https://api.github.com"},
        },
        supports_check_mode=True,
    )
    params = module.params
    api = params["api_url"].rstrip("/")
    token = signed(module, params["app_id"], params["private_key"])

    status, app = call(module, "GET", f"{api}/app", token)
    if status != 200:
        module.fail_json(msg=f"GitHub did not accept the App's credentials (HTTP {status}: {app.get('message', 'no message')}). "
                             "Check github_app_id and github_app_private_key in Vault.")
    events = sorted(app.get("events") or [])
    status, current = call(module, "GET", f"{api}/app/hook/config", token)
    changed = status != 200 or current.get("url") != params["url"]
    if not module.check_mode:
        # The secret cannot be read back, so it is always set: GitHub then signs with the one EDA checks.
        status, updated = call(module, "PATCH", f"{api}/app/hook/config", token,
                               {"url": params["url"], "content_type": "json", "secret": params["secret"],
                                "insecure_ssl": "1" if params["insecure_ssl"] else "0"})
        if status != 200:
            module.fail_json(msg=f"GitHub refused the App's webhook settings (HTTP {status}: {updated.get('message', 'no message')}). "
                                 "In the App's settings, tick Webhook > Active and save once with any address; this sets the real one.")
    module.exit_json(changed=changed, url=params["url"], events=events, push_subscribed="push" in events)


if __name__ == "__main__":
    main()
