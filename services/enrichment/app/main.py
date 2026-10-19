"""ACME Bank AI enrichment service.

Milestone M2 skeleton: it checks the caller's token and the request, and returns a fixed response
that follows the contract in section 5.3 of the implementation design, so the trigger, the workflow
and the write-back can be proved before retrieval and the model are connected (M3).

It holds no ITSM, cluster or AAP credentials (principle P3). Its only secrets are its own API token,
which AAP presents, and its Models-as-a-Service key, which it does not use yet.
"""

import hmac
import os
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

SERVICE_VERSION = "0.1.0-skeleton"
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


class EnrichRequest(BaseModel):
    incident: Incident
    revision: int = Field(default=1, ge=1, le=99)
    evidence: list[dict] = Field(default_factory=list, max_length=50)
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
    return {
        "status": "enriched",
        "summary": (
            f"Skeleton response for {request.incident.number}: the enrichment service is connected, "
            "but evidence, knowledge and the model are not used yet (milestone M2)."
        ),
        "symptoms": [],
        "likely_causes": [],
        "next_steps": [],
        "recommended_job": None,
        "gaps": ["No diagnostic evidence, knowledge or model was used: this is the M2 skeleton."],
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
