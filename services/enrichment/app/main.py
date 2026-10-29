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
Each request is traced in MLflow, step by step (app.tracing), and the trace ID goes into the note.

A failure to reach the knowledge index or the model is an error (503 or 502) with a reason that is
safe to show, so the workflow writes an "AI enrichment unavailable" note saying why. The service
holds no ITSM or AAP credentials (principle P3): only its own API token, its gateway key, the
read-only knowledge identity, and a short-lived token for its service account, which may only write
traces to MLflow.
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

from app import knowledge, model, policy, prompt, retrieval, tracing
from app.sanitise import sanitise, sanitise_tree

SERVICE_VERSION = "0.5.0"
API_TOKEN = os.environ["ENRICHMENT_API_TOKEN"]
MAAS_CONSUMER = os.environ.get("MAAS_CONSUMER", "")

log = logging.getLogger("enrichment")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
state: dict = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Loaded once, before the service reports ready: the model is on disk in the image.
    state["embedder"] = knowledge.embedder()
    # Best effort: if MLflow is down now, each request tries again.
    tracing.ready()
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


class Context(BaseModel):
    """Where the request came from, for the trace's tags (design 5.4, scenario S5)."""

    workflow_job: str = Field(default="", max_length=20, pattern=r"^[0-9]*$")
    event_id: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9 ._:-]*$")


class EnrichRequest(BaseModel):
    incident: Incident
    revision: int = Field(default=1, ge=1, le=99)
    # The affected service's running version, from the diagnostics: retrieval is filtered on it.
    service_version: str = Field(default="", max_length=40, pattern=r"^([0-9]+(\.[0-9A-Za-z-]+)*)?$")
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    catalogue: list[CatalogueEntry] = Field(default_factory=list, max_length=20)
    context: Context = Field(default_factory=Context)


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
    started = time.monotonic()
    fallback_id = str(uuid.uuid4())
    traced = tracing.ready()
    trace_id = None
    try:
        with tracing.span("enrich", "CHAIN") as root:
            trace_id = root.trace_id
            response = _enrich(request, root, trace_id or fallback_id)
    except HTTPException as error:
        # The failure is traced too; its reason, with the trace, goes to the "unavailable" note.
        if traced and tracing.recorded(trace_id):
            error.detail = f"{error.detail} (trace {trace_id})"
        raise
    recorded = traced and tracing.recorded(trace_id)
    provenance = response["provenance"]
    provenance["trace_id"] = trace_id if recorded else fallback_id
    provenance["trace_recorded"] = recorded
    log.info("trace=%s recorded=%s incident=%s status=%s passages=%s tokens=%s model_seconds=%.1f total_seconds=%.1f "
             "redactions=%s answer_redactions=%s", provenance["trace_id"], recorded, request.incident.number,
             response["status"], ",".join(provenance["source_ids"]) or "none",
             provenance["tokens"]["prompt"] + provenance["tokens"]["completion"], provenance["model_seconds"],
             time.monotonic() - started, provenance["redactions"] or "none", provenance["answer_redactions"] or "none")
    return response


def _enrich(request: EnrichRequest, root, trace_ref: str) -> dict:
    # Rule 1: nothing unsanitised goes any further than this, the trace included.
    redactions: Counter = Counter()
    with tracing.span("sanitise", "PARSER") as step:
        incident = request.incident.model_dump()
        incident["short_description"] = sanitise(incident["short_description"], redactions)
        evidence = [{**item.model_dump(), "target": sanitise(item.target, redactions), "fact": sanitise(item.fact, redactions),
                     "ref": sanitise(item.ref, redactions)} for item in request.evidence]
        tracing.safe_outputs(step, {"redactions": dict(redactions)})
    catalogue = [entry.model_dump() for entry in request.catalogue]
    evidence_ids = [item["id"] for item in evidence]
    job_ids = [entry["id"] for entry in catalogue]
    diagnostic_gaps = sum(1 for i in evidence_ids if i.endswith("-GAP"))
    version = request.service_version
    context = request.context.model_dump()
    tracing.safe_inputs(root, {"incident": incident, "service_version": version, "revision": request.revision,
                               "evidence": evidence, "catalogue": job_ids, "context": context})
    tracing.tag({"incident": incident["number"], "service": incident["cmdb_ci"], "service_version": version,
                 "revision": request.revision, "aap_workflow_job": context["workflow_job"], "event_id": context["event_id"],
                 "enrichment_service_version": SERVICE_VERSION, "prompt_version": prompt.PROMPT_VERSION,
                 "policy_version": policy.POLICY_VERSION, "retrieval_version": retrieval.RETRIEVAL_VERSION,
                 "model": model.MAAS_MODEL, "consumer": MAAS_CONSUMER})
    retrieval_gaps: list[str] = []

    # Rule 2.
    with tracing.span("retrieve", "RETRIEVER") as step:
        if not version:
            passages, candidates, verdict = [], [], {"documents": {}, "passed": []}
            retrieval_gaps.append("The service's running version is not known, so no runbook could be matched to it.")
        else:
            tracing.safe_inputs(step, {"queries": retrieval.queries(incident, evidence), "service": incident["cmdb_ci"],
                                       "version": knowledge.major_version(version)})
            try:
                with knowledge.connect() as conn:
                    passages, candidates, verdict = retrieval.retrieve(conn, state["embedder"], incident, evidence,
                                                                       version)
            except Exception as error:  # noqa: BLE001 - any failure here means no knowledge, and is reported as such
                log.warning("trace=%s knowledge index unavailable: %s", trace_ref, type(error).__name__)
                raise HTTPException(status_code=503,
                                    detail=f"The knowledge index could not be searched ({type(error).__name__}).") from None
        chosen = {p["id"] for p in passages}
        tracing.safe_attributes(step, {"document_gate": retrieval.DOCUMENT_GATE,
                                       "gate_scores": ",".join(f"{d}={s}" for d, s in verdict["documents"].items()),
                                       "gate_passed": ",".join(verdict["passed"]),
                                       "threshold": retrieval.THRESHOLD, "max_passages": retrieval.MAX_PASSAGES,
                                       "skip_sections": ",".join(retrieval.SKIP_SECTIONS),
                                       "expand_documents": retrieval.EXPAND_DOCUMENTS,
                                       "added_with_document": ",".join(p["id"] for p in passages if p.get("added_with"))})
        # In MLflow's document format, so its interface shows each passage with its score.
        tracing.safe_outputs(step, [{"id": c["id"], "page_content": c["content"],
                                     "metadata": {"doc_uri": c["id"], "score": c["score"], "sent_to_model": c["id"] in chosen,
                                                  "document_gate_passed": not c.get("gated", False)}}
                                    for c in candidates])
    insufficient = not passages
    if insufficient and version:
        target = f"{incident['cmdb_ci'] or 'this service'} {knowledge.major_version(version)}"
        if not verdict["passed"]:
            top = max(verdict["documents"].items(), key=lambda kv: kv[1], default=None)
            best = f" (closest {top[0]} at {top[1]:.2f}, needs {retrieval.DOCUMENT_GATE:.2f})" if top else ""
            retrieval_gaps.append(f"No approved runbook or resolution for {target} addresses the failure this incident "
                                  f"describes{best}, so there is no documented fix.")
        else:
            best = f" (best match {candidates[0]['id']} at {candidates[0]['score']:.2f})" if candidates else ""
            retrieval_gaps.append(f"No approved runbook or resolution for {target} met the relevance threshold of "
                                  f"{retrieval.THRESHOLD:.2f}{best}.")
    passage_ids = [p["id"] for p in passages]

    # Rule 3.
    schema = prompt.schema(evidence_ids, passage_ids, job_ids, insufficient)
    user = prompt.user_message(incident, version, evidence, passages, catalogue, insufficient)
    with tracing.span("model", "CHAT_MODEL",
                      {"messages": [{"role": "system", "content": prompt.SYSTEM}, {"role": "user", "content": user}],
                       "response_schema": schema}) as step:
        tracing.safe_attributes(step, {"model": model.MAAS_MODEL, "temperature": model.TEMPERATURE,
                                       "max_tokens": model.MAX_TOKENS, "insufficient_schema": insufficient})
        try:
            answer, tokens, seconds = model.complete(prompt.SYSTEM, user, schema)
        except model.ModelError as error:
            log.warning("trace=%s model call failed: %s", trace_ref, error)
            raise HTTPException(status_code=502, detail=str(error)) from None
        # Anything the model wrote that looks like a secret is removed before it is traced or returned.
        answer_redactions: Counter = Counter()
        answer = sanitise_tree(answer, answer_redactions)
        tracing.safe_outputs(step, answer)
        tracing.safe_attributes(step, {"tokens.prompt": tokens["prompt"], "tokens.completion": tokens["completion"],
                                       "seconds": round(seconds, 1)})

    # Rules 4 and 5.
    with tracing.span("check", "PARSER") as step:
        try:
            checked = policy.apply(answer, evidence_ids, passage_ids, job_ids, diagnostic_gaps)
        except policy.AnswerError as error:
            log.warning("trace=%s model answer refused: %s", trace_ref, error)
            raise HTTPException(status_code=502, detail=f"The model's answer did not follow the schema: {error}.") from None
        checked["gaps"] = policy.merge_gaps(retrieval_gaps, checked["gaps"])
        tracing.safe_outputs(step, {"answer": checked, "answer_redactions": dict(answer_redactions)})

    response = {
        **checked,
        # What the answer was based on, as the model saw it: sanitised evidence and the passages used.
        "evidence_considered": [{"id": e["id"], "source": e["source"], "fact": e["fact"]} for e in evidence],
        "knowledge_used": [{"id": p["id"], "title": f"{p['doc_title']}: {p['section']}", "score": p["score"],
                            "added_with": p.get("added_with")} for p in passages],
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
            "candidates": [{"id": c["id"], "score": c["score"], "gated": c.get("gated", False)} for c in candidates[:10]],
            "document_gate": {"bar": retrieval.DOCUMENT_GATE, "scores": verdict["documents"], "passed": verdict["passed"]},
            "redactions": dict(redactions),
            "answer_redactions": dict(answer_redactions),
            "tokens": tokens,
            "model_seconds": round(seconds, 1),
            "revision": request.revision,
        },
    }
    tracing.tag({"outcome": checked["status"], "manual_review_required": checked["manual_review_required"],
                 "suggestions": len(checked["suggestions"])})
    tracing.safe_outputs(root, {k: v for k, v in checked.items()})
    return response
