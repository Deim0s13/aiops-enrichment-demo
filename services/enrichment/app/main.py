"""ACME Bank AI enrichment service (design 5.3).

For each request from the AAP workflow it:
1. checks the caller's token and the request, including every evidence item (design 5.2);
2. sanitises the evidence and the incident's description (app.sanitise, rule 1);
3. retrieves approved passages for the incident's service and version, as the read-only identity,
   keeping only those at or above the relevance threshold (app.retrieval, rule 2);
4. asks the model through the gateway, constrained to a schema built for this request (app.prompt,
   app.model, rule 3);
5. checks the answer: citations, the catalogue, grounding and manual review (app.policy, rules 4, 5);
6. returns the answer with the evidence it considered, the passages it used and its provenance.

A failure to reach the knowledge index or the model is an error (503 or 502) with a reason that is
safe to show, so the workflow writes an "AI enrichment unavailable" note saying why. The service
holds no ITSM, cluster or AAP credentials (principle P3): only its own API token, its gateway key and
the read-only knowledge identity.
"""

import hmac
import logging
import os
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import knowledge, model, policy, prompt, retrieval
from app.sanitise import sanitise, sanitise_tree

SERVICE_VERSION = "0.3.0"
API_TOKEN = os.environ["ENRICHMENT_API_TOKEN"]
MAAS_CONSUMER = os.environ.get("MAAS_CONSUMER", "")

log = logging.getLogger("enrichment")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
state: dict = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Loaded once, before the service reports ready: the model is on disk in the image.
    state["embedder"] = knowledge.embedder()
    yield


# No interactive API documentation: the contract is in the design, not served to callers.
app = FastAPI(title="ACME AI enrichment", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


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
    source: str = Field(max_length=60, pattern=r"^[A-Za-z0-9._-]*$")
    collected_at: str = Field(default="", max_length=30)
    target: str = Field(default="", max_length=200)
    fact: str = Field(max_length=4096)
    ref: str = Field(default="", max_length=300)


class CatalogueEntry(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    description: str = Field(max_length=600)


class EnrichRequest(BaseModel):
    incident: Incident
    revision: int = Field(default=1, ge=1, le=99)
    # The affected service's running version, from the diagnostics: retrieval is filtered on it.
    service_version: str = Field(default="", max_length=40, pattern=r"^([0-9]+(\.[0-9A-Za-z-]+)*)?$")
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    catalogue: list[CatalogueEntry] = Field(default_factory=list, max_length=20)


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
    trace_id = str(uuid.uuid4())
    started = time.monotonic()

    # Rule 1: nothing unsanitised goes any further than this.
    redactions: Counter = Counter()
    incident = request.incident.model_dump()
    incident["short_description"] = sanitise(incident["short_description"], redactions)
    evidence = [{**item.model_dump(), "target": sanitise(item.target, redactions), "fact": sanitise(item.fact, redactions),
                 "ref": sanitise(item.ref, redactions)} for item in request.evidence]
    catalogue = [entry.model_dump() for entry in request.catalogue]
    evidence_ids = [item["id"] for item in evidence]
    job_ids = [entry["id"] for entry in catalogue]
    diagnostic_gaps = sum(1 for i in evidence_ids if i.endswith("-GAP"))
    version = request.service_version
    retrieval_gaps: list[str] = []

    # Rule 2.
    if not version:
        passages, candidates = [], []
        retrieval_gaps.append("The service's running version is not known, so no runbook could be matched to it.")
    else:
        try:
            with knowledge.connect() as conn:
                passages, candidates = retrieval.retrieve(conn, state["embedder"], incident, evidence, version)
        except Exception as error:  # noqa: BLE001 - any failure here means no knowledge, and is reported as such
            log.warning("trace=%s knowledge index unavailable: %s", trace_id, type(error).__name__)
            raise HTTPException(status_code=503, detail=f"The knowledge index could not be searched ({type(error).__name__}).") from None
    insufficient = not passages
    if insufficient and version:
        best = f" (best match {candidates[0]['id']} at {candidates[0]['score']:.2f})" if candidates else ""
        retrieval_gaps.append(f"No approved runbook or resolution for {incident['cmdb_ci'] or 'this service'} "
                              f"{knowledge.major_version(version)} met the relevance threshold of {retrieval.THRESHOLD:.2f}{best}.")
    passage_ids = [p["id"] for p in passages]

    # Rule 3.
    schema = prompt.schema(evidence_ids, passage_ids, job_ids, insufficient)
    user = prompt.user_message(incident, version, evidence, passages, catalogue, insufficient)
    try:
        answer, tokens, seconds = model.complete(prompt.SYSTEM, user, schema)
    except model.ModelError as error:
        log.warning("trace=%s model call failed: %s", trace_id, error)
        raise HTTPException(status_code=502, detail=str(error)) from None

    # Rules 4 and 5, and anything the model wrote that looks like a secret.
    answer_redactions: Counter = Counter()
    try:
        checked = policy.apply(sanitise_tree(answer, answer_redactions), evidence_ids, passage_ids, job_ids, diagnostic_gaps)
    except policy.AnswerError as error:
        log.warning("trace=%s model answer refused: %s", trace_id, error)
        raise HTTPException(status_code=502, detail=f"The model's answer did not follow the schema: {error}.") from None
    checked["gaps"] = (retrieval_gaps + checked["gaps"])[:policy.LIMITS["gaps"]]

    log.info("trace=%s incident=%s status=%s passages=%s tokens=%s model_seconds=%.1f total_seconds=%.1f redactions=%s answer_redactions=%s",
             trace_id, incident["number"], checked["status"], ",".join(passage_ids) or "none",
             tokens["prompt"] + tokens["completion"], seconds, time.monotonic() - started, dict(redactions) or "none",
             dict(answer_redactions) or "none")

    return {
        **checked,
        # What the answer was based on, as the model saw it: sanitised evidence and the passages used.
        "evidence_considered": [{"id": e["id"], "source": e["source"], "fact": e["fact"]} for e in evidence],
        "knowledge_used": [{"id": p["id"], "title": f"{p['doc_title']}: {p['section']}", "score": p["score"]}
                           for p in passages],
        "provenance": {
            "service_version": SERVICE_VERSION,
            "consumer": MAAS_CONSUMER,
            "model": model.MAAS_MODEL,
            "prompt_version": prompt.PROMPT_VERSION,
            "policy_version": policy.POLICY_VERSION,
            "retrieval_version": retrieval.RETRIEVAL_VERSION,
            "service": incident["cmdb_ci"],
            "target_version": version,
            "source_ids": passage_ids,
            "candidates": [{"id": c["id"], "score": c["score"]} for c in candidates[:10]],
            "redactions": dict(redactions),
            "answer_redactions": dict(answer_redactions),
            "trace_id": trace_id,
            "tokens": tokens,
            "model_seconds": round(seconds, 1),
            "revision": request.revision,
        },
    }
