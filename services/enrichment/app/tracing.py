"""Tracing of every enrichment request in MLflow (DD07, DD23).

One trace per request, in the experiment MLFLOW_EXPERIMENT_NAME of the service's own workspace (its
namespace), with a span for each step: sanitisation, retrieval, the model call and the service's
checks. The trace holds the sanitised evidence, the passages, the prompt and the model's answer, and
is tagged with the incident, the versions in use and the AAP workflow job, so a work note can be
followed to exactly what produced it.

The service signs in to MLflow with a short-lived token for its service account, which OpenShift
mounts and renews (MLFLOW_TRACKING_AUTH=kubernetes-namespaced). Tracing is best effort: if MLflow
cannot be reached, enrichment carries on, and the answer says the trace was not recorded. MLflow's
own retries are turned off, its timeout is three seconds, and after a failure it is left alone for a
minute, so an MLflow outage costs one request a few seconds, not every request minutes. A trace is
only reported as recorded once it has been read back.
"""

import logging
import os
import time
from contextlib import contextmanager

log = logging.getLogger("enrichment.tracing")

TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "")
EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT_NAME", "aiops-enrichment")
ENABLED = bool(TRACKING_URI) and os.environ.get("ENRICHMENT_TRACING", "on") != "off"

# Set before MLflow is imported: export in the request rather than in the background, so the trace can
# be read back before the answer is returned; and fail fast rather than retrying for minutes.
os.environ.setdefault("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "false")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "3")
os.environ.setdefault("MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "true")
# MLflow's client otherwise reports usage to an external telemetry service. Nothing leaves the cluster.
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
os.environ.setdefault("DO_NOT_TRACK", "true")

# After a failure, MLflow is not tried again for this long, so an outage costs one request the
# timeout, not every request.
RETRY_AFTER = 60
_state = {"experiment_id": None, "failed_at": None}


class _NoSpan:
    """Stands in for a span when tracing is off, so the service's code is the same either way."""

    trace_id = None

    def set_inputs(self, *_args, **_kwargs):
        pass

    def set_outputs(self, *_args, **_kwargs):
        pass

    def set_attributes(self, *_args, **_kwargs):
        pass


def _mlflow():
    import mlflow

    return mlflow


def ready() -> bool:
    """Points MLflow at the experiment, creating it the first time. Tried again a minute after a
    failure, so a service started while MLflow was down starts tracing once MLflow is back."""
    if not ENABLED:
        return False
    if _state["experiment_id"]:
        return True
    if _state["failed_at"] and time.monotonic() - _state["failed_at"] < RETRY_AFTER:
        return False
    try:
        mlflow = _mlflow()
        mlflow.set_tracking_uri(TRACKING_URI)
        _state["experiment_id"] = mlflow.set_experiment(EXPERIMENT).experiment_id
        log.info("tracing to experiment %s (%s)", EXPERIMENT, _state["experiment_id"])
        return True
    except Exception as error:  # noqa: BLE001 - tracing must never stop enrichment
        _state["failed_at"] = time.monotonic()
        log.warning("MLflow is not available, so requests are not traced for the next %s seconds: %s",
                    RETRY_AFTER, str(error)[:300])
        return False


@contextmanager
def span(name: str, span_type: str = "UNKNOWN", inputs=None):
    """A span in the current trace, or a stand-in when tracing is off. Exceptions raised inside it
    are recorded on the span and passed on."""
    if not ENABLED or not _state["experiment_id"]:
        yield _NoSpan()
        return
    mlflow = _mlflow()
    with mlflow.start_span(name=name, span_type=span_type) as current:
        if inputs is not None:
            _safe(current.set_inputs, inputs)
        yield current


def tag(tags: dict) -> None:
    if ENABLED and _state["experiment_id"]:
        _safe(_mlflow().update_current_trace, tags={k: str(v) for k, v in tags.items() if v not in (None, "")})


def recorded(trace_id: str | None) -> bool:
    """True only if MLflow has the trace: it is read back, not assumed."""
    if not trace_id or not ENABLED or not _state["experiment_id"] or trace_id.startswith("MLFLOW_NO_OP"):
        return False
    try:
        found = _mlflow().get_trace(trace_id, silent=True) is not None
    except Exception:  # noqa: BLE001
        found = False
    if not found:
        # MLflow has gone away since the experiment was set: stop trying for a while.
        _state["experiment_id"], _state["failed_at"] = None, time.monotonic()
        log.warning("trace %s was not recorded; requests are not traced for the next %s seconds", trace_id, RETRY_AFTER)
    return found


def _safe(function, *args, **kwargs) -> None:
    try:
        function(*args, **kwargs)
    except Exception as error:  # noqa: BLE001
        log.debug("tracing call failed: %s", error)


def safe_inputs(current, value) -> None:
    _safe(current.set_inputs, value)


def safe_outputs(current, value) -> None:
    _safe(current.set_outputs, value)


def safe_attributes(current, value: dict) -> None:
    _safe(current.set_attributes, value)
