"""The model call, through the OpenShift AI gateway with the service's own key (DD14, ADR06).

The gateway is OpenAI-compatible. The answer is constrained to the request's JSON schema, so it is
always parseable and can only cite what the request supplied; the service still checks it (app.policy).
Any failure is raised as ModelError with a reason that is safe to show: it never carries the key.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request

MAAS_URL = os.environ.get("MAAS_URL", "").rstrip("/")
MAAS_MODEL = os.environ.get("MAAS_MODEL", "")
MAAS_API_KEY = os.environ.get("MAAS_API_KEY", "")
# Model-specific request fields, such as Qwen3's switch for its thinking mode, set by the build from the
# inventory so the service itself does not depend on one model.
MAAS_REQUEST_EXTRA = json.loads(os.environ.get("MAAS_REQUEST_EXTRA", "") or "{}")
MAAS_TIMEOUT = float(os.environ.get("MAAS_TIMEOUT", "75"))
MAAS_CA_FILE = os.environ.get("MAAS_CA_FILE", "")
TEMPERATURE = float(os.environ.get("ENRICHMENT_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.environ.get("ENRICHMENT_MAX_TOKENS", "1200"))


class ModelError(RuntimeError):
    pass


def complete(system: str, user: str, schema: dict) -> tuple[dict, dict, float]:
    """Returns the model's answer as a dict, the token usage, and the seconds the call took."""
    if not (MAAS_URL and MAAS_MODEL and MAAS_API_KEY):
        raise ModelError("The service has no model gateway address, model name or key (MAAS_URL, MAAS_MODEL, MAAS_API_KEY).")
    body = {
        "model": MAAS_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "enrichment", "strict": True, "schema": schema}},
        **MAAS_REQUEST_EXTRA,
    }
    request = urllib.request.Request(
        f"{MAAS_URL}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {MAAS_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    context = ssl.create_default_context(cafile=MAAS_CA_FILE or None)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=MAAS_TIMEOUT, context=context) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        hint = {401: "the key was refused", 403: "the key is not allowed this model",
                429: "the consumer's token limit is reached", 404: "the model is not served at this address"}
        raise ModelError(f"The model gateway answered HTTP {error.code}"
                         f"{': ' + hint[error.code] if error.code in hint else ''}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        timed_out = f" (timed out after {MAAS_TIMEOUT:.0f} seconds)" if "timed out" in str(reason) else ""
        raise ModelError(f"The model gateway could not be reached: {type(reason).__name__}{timed_out}.") from None
    except json.JSONDecodeError:
        raise ModelError("The model gateway's answer was not JSON.") from None
    seconds = time.monotonic() - started

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ModelError("The model gateway's answer had no message.") from None
    if choice.get("finish_reason") == "length":
        raise ModelError(f"The model's answer was cut off at {MAX_TOKENS} tokens.")
    try:
        answer = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        raise ModelError("The model's answer was not the JSON the schema requires.") from None
    if not isinstance(answer, dict):
        raise ModelError("The model's answer was not a JSON object.")
    usage = payload.get("usage") or {}
    tokens = {"prompt": int(usage.get("prompt_tokens", 0)), "completion": int(usage.get("completion_tokens", 0))}
    return answer, tokens, seconds
