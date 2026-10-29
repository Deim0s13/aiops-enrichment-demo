"""Retrieval for one incident (design 5.3, rule 2; DD21, DD24).

Each evidence item asks its own question of the index, together with the incident's description: the
pod's termination, the log's warnings and the running configuration each point at a different section
of a runbook, and one long query made of all of them would blur those together (the embedding model
also reads only the first 512 tokens). A passage scores the best of its matches.

Sections that describe a document or its service rather than say what to do (its Purpose, Scope,
Service overview, Related documents, Change history and Timeline) are not searched: they are short and mention every keyword, so they
outranked the runbook's Diagnosis and Actions in the first cluster runs, and the model was left
without the documented fix. Instead, the best-matching runbook brings its Diagnosis and Actions, and
the best-matching resolution its Root cause and Resolution. A runbook is meant to be followed, not
sampled.

First, a gate (DD27): a document may reach the model only if it is relevant to the incident's own
description, the failure the alert states. Evidence about other conditions, such as a heap setting
that every memory runbook discusses, would otherwise bring a document in on its own, and the model
then bends the evidence to fit it, as it did in the first runs of scenario S2. Then only passages of
documents that passed, at or above the relevance threshold, are chosen; if none is, there is no
documented fix and the answer can only be insufficient_evidence (app.prompt). Retrieval is always filtered on the
incident's service and its major version, and runs as the read-only identity, which can see
approved, internal passages only.
"""

import os
import re

from app import knowledge

THRESHOLD = float(os.environ.get("ENRICHMENT_RELEVANCE_THRESHOLD", "0.75"))
MAX_PASSAGES = int(os.environ.get("ENRICHMENT_MAX_PASSAGES", "5"))
# How many documents of each type bring their actionable sections: the best runbook and the best resolution.
EXPAND_DOCUMENTS = int(os.environ.get("ENRICHMENT_EXPAND_DOCUMENTS", "1"))
SKIP_SECTIONS = tuple(s.strip() for s in os.environ.get(
    "ENRICHMENT_SKIP_SECTIONS", "Purpose,Scope,Service overview,Related documents,Change history,Timeline").split(",") if s.strip())
# The sections that say what to do, by document type, in the order the model should read them.
ACTIONABLE = {"runbook": ("Diagnosis", "Actions"), "resolution": ("Root cause", "Resolution")}
# A document reaches the model only if its best passage scores at least this against the incident's
# description alone (DD27). Set from measurement (2026-10-29): the memory fault's description scored
# 0.79 against its runbook, the throttling fault's 0.65 against anything.
DOCUMENT_GATE = float(os.environ.get("ENRICHMENT_DOCUMENT_GATE", "0.72"))
GATE_LIMIT = 50
PER_QUERY = 5
RETRIEVAL_VERSION = (f"{knowledge.EMBED_MODEL.split('/')[-1]}|exact|gate{DOCUMENT_GATE:.2f}|per-evidence-max|no-service-name|"
                     f"skip-navigation|expand{EXPAND_DOCUMENTS}-per-type|t{THRESHOLD:.2f}|k{MAX_PASSAGES}")


def queries(incident: dict, evidence: list[dict]) -> list[str]:
    """The incident's description, then one question per evidence item that is not a gap. The
    service's own name is taken out: every candidate is already for that service, so its name only
    pulls every document closer and hides the difference between a fault a runbook covers and one it
    does not."""
    service = incident.get("cmdb_ci", "")

    def strip(text: str) -> str:
        # Pod names start with the service's name, so they go too.
        return " ".join(re.sub(rf"\b{re.escape(service)}[-a-z0-9]*", " ", text).split()) if service else text.strip()

    description = strip(incident.get("short_description", ""))
    asked = [description] if description else []
    for item in evidence:
        if not item["id"].endswith("-GAP"):
            asked.append(f"{description}\n{strip(item['fact'])}".strip())
    return asked


def gate(conn, embedder, incident: dict, version: str) -> dict:
    """The document-level relevance gate (DD27): each document's best score against the incident's
    description alone, and which documents pass. Only those may reach the model. Evidence about other
    conditions, such as a risky setting, can match a document well; it must not bring that document
    in on its own."""
    service = incident.get("cmdb_ci", "")
    description = queries(incident, [])
    scores: dict[str, float] = {}
    if description:
        for row in knowledge.search(conn, embedder.query(description[0]), service, version, limit=GATE_LIMIT,
                                    skip_sections=SKIP_SECTIONS):
            scores.setdefault(row["doc_id"], round(float(row["score"]), 3))
    return {"documents": scores, "passed": sorted(d for d, s in scores.items() if s >= DOCUMENT_GATE)}


def retrieve(conn, embedder, incident: dict, evidence: list[dict], version: str) -> tuple[list[dict], list[dict], dict]:
    """Returns the passages to send to the model, every candidate considered with its score, and the
    gate's verdict. A passage added with its document carries added_with: the ID of the passage that
    matched."""
    service = incident.get("cmdb_ci", "")
    if not service or not knowledge.major_version(version):
        return [], [], {"documents": {}, "passed": []}
    verdict = gate(conn, embedder, incident, version)
    allowed = set(verdict["passed"])
    best: dict[str, dict] = {}
    for question in queries(incident, evidence):
        for row in knowledge.search(conn, embedder.query(question), service, version, limit=PER_QUERY,
                                    skip_sections=SKIP_SECTIONS):
            row["gated"] = row["doc_id"] not in allowed
            row["score"] = round(float(row["score"]), 3)
            if row["id"] not in best or row["score"] > best[row["id"]]["score"]:
                best[row["id"]] = row
    ranked = sorted(best.values(), key=lambda r: r["score"], reverse=True)
    chosen = [dict(r, added_with=None) for r in ranked if r["score"] >= THRESHOLD and not r["gated"]][:MAX_PASSAGES]

    # The best-matching runbook and the best-matching resolution bring their actionable sections, if
    # not already chosen. One of each, not the two best overall: past resolutions often outscore the
    # runbook, and the runbook is the current procedure.
    have = {p["id"] for p in chosen}
    documents: list[dict] = []
    for doc_type in ACTIONABLE:
        seen: list[str] = []
        for passage in chosen:
            if passage["type"] == doc_type and passage["doc_id"] not in seen:
                seen.append(passage["doc_id"])
                if len(seen) <= EXPAND_DOCUMENTS:
                    documents.append(passage)
    for top in documents:
        for extra in knowledge.sections(conn, top["doc_id"], ACTIONABLE.get(top["type"], ())):
            if extra["id"] not in have:
                have.add(extra["id"])
                chosen.append(dict(extra, score=best.get(extra["id"], {}).get("score"), added_with=top["id"]))
    return chosen, ranked, verdict
