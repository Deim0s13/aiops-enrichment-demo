"""The service's checks on the model's answer (design 5.3, rules 3 to 5; DD24), version 2.

The schema already constrains the answer, but a decoder may ignore a keyword it does not support, so
nothing is taken on trust:
- the answer must have the schema's fields, of the right kinds (rule 3), or the call fails;
- a cause or step citing an ID that was not supplied is dropped, and checks_removed says so (rule 4);
- a recommended job not in the catalogue is dropped (rule 4);
- a next step that cites no approved passage is not documented, so it becomes a low-trust
  suggestion to fix, if it cites evidence, rather than passing as the documented fix;
- a suggestion may cite only observed evidence, never a passage or a gap, and never carries a job;
- an "enriched" answer that cites no retrieved passage is not grounded in approved knowledge, so it
  becomes insufficient_evidence, with its steps kept as suggestions (rule 5);
- an insufficient_evidence answer has no next steps and no job;
- manual review is required whenever a diagnostic left a gap, the answer is insufficient, or it
  carries suggestions.
Change POLICY_VERSION with any change here.
"""

import re

POLICY_VERSION = "policy-v2"
# A model sometimes fills a list with a placeholder rather than leaving it empty.
_PLACEHOLDER = re.compile(r"^(none|none noted|no gaps?|n/?a|nothing)\.?$", re.I)

LIMITS = {"symptoms": 6, "likely_causes": 3, "next_steps": 5, "suggestions": 4, "gaps": 8}
KINDS = ("investigate", "fix")
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
    required = ("status", "summary", "symptoms", "likely_causes", "next_steps", "suggestions", "recommended_job", "gaps",
                "manual_review_required")
    missing = [f for f in required if f not in answer]
    if missing:
        raise AnswerError(f"missing {', '.join(missing)}")
    status = answer["status"]
    if status not in ("enriched", "insufficient_evidence"):
        raise AnswerError(f"status {status!r} is not allowed")

    known = set(evidence_ids) | set(passage_ids)
    # What the checks removed, reported apart from the gaps, which are about the evidence.
    notes: list[str] = []
    knowledge_gaps: list[str] = []

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

    # Low-trust suggestions: grounded in what was observed, and nothing else.
    observed = {i for i in evidence_ids if not i.endswith("-GAP")}
    if not isinstance(answer["suggestions"], list):
        raise AnswerError("suggestions is not a list")
    suggestions = []
    for item in answer["suggestions"]:
        keys = ("action", "reason", "risk")
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in keys):
            raise AnswerError("an item in suggestions does not have the schema's fields")
        citations = [c for c in item.get("citations") or [] if c in observed]
        if not citations or not item["action"].strip():
            notes.append("One suggestion was left out: it cited no observed evidence.")
            continue
        suggestions.append({"kind": item.get("kind") if item.get("kind") in KINDS else "investigate",
                            **{k: item[k].strip() for k in keys}, "citations": list(dict.fromkeys(citations))})

    # A step with no approved passage behind it is the model's idea, not the documented fix.
    documented = []
    for step in steps:
        if set(step["citations"]) & set(passage_ids):
            documented.append(step)
        else:
            suggestions.append(_as_suggestion(step, observed))
    steps = documented

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
        knowledge_gaps.append("No cause or step cites an approved runbook or resolution, so there is no documented fix.")
    if status == "insufficient_evidence":
        suggestions += [_as_suggestion(step, observed) for step in steps]
        steps, job = [], None
    suggestions = [s for s in suggestions if s["citations"]][:LIMITS["suggestions"]]

    gaps = knowledge_gaps + [g for g in _texts(answer["gaps"], "gaps") if not _PLACEHOLDER.match(g)]
    return {
        "status": status,
        "summary": _text(answer["summary"], "summary"),
        "symptoms": _texts(answer["symptoms"], "symptoms")[:LIMITS["symptoms"]],
        "likely_causes": causes,
        "next_steps": steps,
        "suggestions": suggestions,
        "recommended_job": job,
        "gaps": gaps[:LIMITS["gaps"]],
        "checks_removed": notes,
        "manual_review_required": bool(answer["manual_review_required"]) or status == "insufficient_evidence"
        or diagnostic_gaps > 0 or bool(notes) or bool(suggestions),
    }


def _as_suggestion(step: dict, observed: set) -> dict:
    """A next step without an approved passage behind it, kept as a low-trust suggestion to fix."""
    reason = " ".join(part for part in (step["prerequisites"] and f"Prerequisites: {step['prerequisites']}",
                                        step["verify"] and f"Verify: {step['verify']}") if part)
    return {"kind": "fix", "action": step["step"], "reason": reason, "risk": step["risk"],
            "citations": [c for c in step["citations"] if c in observed]}
