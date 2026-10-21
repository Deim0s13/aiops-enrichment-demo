"""ACME Bank AI enrichment service.

Skeleton until milestone M4: it checks the caller's token and the request, including the evidence
items in the format of design 5.2, and returns a response that follows the contract in section 5.3.
It reports the evidence it received as symptoms, citing each item's ID, and the diagnostics' gaps,
but draws no conclusions: retrieval and the model arrive in M4.

It holds no ITSM, cluster or AAP credentials (principle P3). Its only secrets are its own API token,
which AAP presents, and its Models-as-a-Service key, which it does not use yet.
"""

import hmac
import os
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

SERVICE_VERSION = "0.2.0-skeleton"
API_TOKEN = os.environ["ENRICHMENT_API_TOKEN"]
MAAS_MODEL = os.environ.get("MAAS_MODEL", "")
MAAS_CONSUMER = os.environ.get("MAAS_CONSUMER", "")

# No interactive API documentation: the contract is in the design, not served to callers.
app = FastAPI(title="ACME AI enrichment", docs_url=None, redoc_url=None, openapi_url=None)


class Incident(BaseModel):
    sys_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    number: str = Field(pattern=r"^INC[0-9]{7,}$")
    short_description: str = Field(default="", max_length=160)
    cmdb_ci: str = Field(default="", max_length=100)
    priority: str = Field(default="", max_length=2)
    opened_at: str = Field(default="", max_length=30)


class Evidence(BaseModel):
    """One evidence item (design 5.2). A gap item's ID ends in -GAP."""

    id: str = Field(pattern=r"^EV-[A-Z]{2,5}-([0-9]{2}|GAP)$")
    source: str = Field(max_length=60)
    collected_at: str = Field(default="", max_length=30)
    target: str = Field(default="", max_length=200)
    fact: str = Field(max_length=4096)
    ref: str = Field(default="", max_length=300)


class EnrichRequest(BaseModel):
    incident: Incident
    revision: int = Field(default=1, ge=1, le=99)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    catalogue: list[dict] = Field(default_factory=list, max_length=20)


def authorise(authorization: str | None) -> None:
    expected = f"Bearer {API_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or wrong token.")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "version": SERVICE_VERSION}


@app.post("/v1/enrich")
def enrich(request: EnrichRequest, authorization: str | None = Header(default=None)) -> dict:
    authorise(authorization)
    found = [item for item in request.evidence if not item.id.endswith("-GAP")]
    missing = [item for item in request.evidence if item.id.endswith("-GAP")]
    return {
        "status": "enriched",
        "summary": (
            f"Skeleton response for {request.incident.number}: {len(found)} evidence item(s) received from the "
            f"diagnostics and {len(missing)} gap(s). Knowledge and the model are not used yet (milestone M4), "
            "so no causes or next steps are given."
        ),
        "symptoms": [f"{item.fact} [{item.id}]" for item in found],
        "likely_causes": [],
        "next_steps": [],
        "recommended_job": None,
        "gaps": [f"{item.fact} [{item.id}]" for item in missing]
        + ["No knowledge or model was used: this is the skeleton until milestone M4."],
        "manual_review_required": True,
        "provenance": {
            "service_version": SERVICE_VERSION,
            "consumer": MAAS_CONSUMER,
            "model": MAAS_MODEL,
            "prompt_version": "none",
            "policy_version": "none",
            "retrieval_version": "none",
            "source_ids": [],
            "trace_id": str(uuid.uuid4()),
            "tokens": {"prompt": 0, "completion": 0},
            "revision": request.revision,
        },
    }
