"""Shared by the knowledge bot's modules (DD33, DD34): signing as the GitHub App, and calling the API."""

import base64
import json
import time

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
    """Calls the GitHub API and returns the HTTP status and the parsed answer."""
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


def signed(module, app_id, private_key):
    """The App's JSON Web Token, or a clear failure if the key cannot be used."""
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg="The cryptography Python package is needed to sign the App's token.")
    try:
        return app_jwt(app_id, private_key)
    except (ValueError, TypeError) as error:
        module.fail_json(msg=f"The App's private key could not be read: {type(error).__name__}. "
                             "Check github_app_private_key in Vault.")
