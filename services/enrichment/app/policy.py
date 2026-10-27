"""The service's checks on the model's answer (design 5.3, rules 3 to 5), version 1.

The schema already constrains the answer, but a decoder may ignore a keyword it does not support, so
nothing is taken on trust:
- the answer must have the schema's fields, of the right kinds (rule 3), or the call fails;
- a cause or step citing an ID that was not supplied is dropped, and the gap says so (rule 4);
- a recommended job not in the catalogue is dropped (rule 4);
- an "enriched" answer that cites no retrieved passage is not grounded in approved knowledge, so it
  becomes insufficient_evidence (rule 5);
- an insufficient_evidence answer has no next steps and no job;
- manual review is required whenever a diagnostic left a gap or the answer is insufficient.
Change POLICY_VERSION with any change here.
"""

import re

POLICY_VERSION = "policy-v1"
# A model sometimes fills a list with a placeholder rather than leaving it empty.
_PLACEHOLDER = re.compile(r"^(none|none noted|no gaps?|n/?a|nothing)\.?$", re.I)

LIMITS = {"symptoms": 6, "likely_causes": 3, "next_steps": 5, "gaps": 8}
CONFIDENCE = ("high", "medium", "low")


class AnswerError(ValueError):
    pass


def _text(value, field: str) -> str:
    if not isinstance(value, str):
        raise AnswerError(f"{field} is not text")
    return value.strip()


def _texts(value, field: str) -> list[str]:
    if not isinstance(value, list):
        raise AnswerError(f"{field} is not a list")
    return [t for t in (_text(v, field) for v in value) if t]


def apply(answer: dict, evidence_ids: list[str], passage_ids: list[str], job_ids: list[str],
          diagnostic_gaps: int) -> dict:
    required = ("status", "summary", "symptoms", "likely_causes", "next_steps", "recommended_job", "gaps",
                "manual_review_required")
    missing = [f for f in required if f not in answer]
    if missing:
        raise AnswerError(f"missing {', '.join(missing)}")
    status = answer["status"]
    if status not in ("enriched", "insufficient_evidence"):
        raise AnswerError(f"status {status!r} is not allowed")

    known = set(evidence_ids) | set(passage_ids)
    notes: list[str] = []

    def cited(items, field: str, keys: tuple[str, ...]) -> list[dict]:
        if not isinstance(items, list):
            raise AnswerError(f"{field} is not a list")
        kept = []
        for item in items:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in keys):
                raise AnswerError(f"an item in {field} does not have the schema's fields")
            citations = item.get("citations")
            if not isinstance(citations, list) or not citations or not set(citations) <= known:
                notes.append(f"One {field.replace('_', ' ').rstrip('s')} was left out: it cited nothing, or an ID "
                             "that was not supplied with the request.")
                continue
            clean = {k: item[k].strip() for k in keys}
            clean["citations"] = list(dict.fromkeys(citations))
            kept.append(clean)
        return kept[:LIMITS[field]]

    causes = cited(answer["likely_causes"], "likely_causes", ("statement", "confidence"))
    for cause in causes:
        if cause["confidence"] not in CONFIDENCE:
            cause["confidence"] = "low"
    steps = cited(answer["next_steps"], "next_steps", ("step", "prerequisites", "risk", "verify"))

    job = answer["recommended_job"]
    if job is not None:
        if not isinstance(job, dict) or job.get("job_id") not in job_ids:
            notes.append("The recommended job was left out: it is not in the catalogue supplied with the request.")
            job = None
        else:
            inputs = job.get("inputs") if isinstance(job.get("inputs"), dict) else {}
            job = {"job_id": job["job_id"], "reason": _text(job.get("reason", ""), "recommended_job.reason"),
                   "inputs": {str(k): str(v) for k, v in inputs.items()}}

    grounded = any(set(item["citations"]) & set(passage_ids) for item in causes + steps)
    if status == "enriched" and not grounded:
        status = "insufficient_evidence"
        notes.append("No cause or step cites an approved knowledge passage, so no next steps are given.")
    if status == "insufficient_evidence":
        steps, job = [], None

    gaps = [g for g in _texts(answer["gaps"], "gaps") if not _PLACEHOLDER.match(g)] + notes
    return {
        "status": status,
        "summary": _text(answer["summary"], "summary"),
        "symptoms": _texts(answer["symptoms"], "symptoms")[:LIMITS["symptoms"]],
        "likely_causes": causes,
        "next_steps": steps,
        "recommended_job": job,
        "gaps": gaps[:LIMITS["gaps"]],
        "manual_review_required": bool(answer["manual_review_required"]) or status == "insufficient_evidence"
        or diagnostic_gaps > 0 or bool(notes),
    }
