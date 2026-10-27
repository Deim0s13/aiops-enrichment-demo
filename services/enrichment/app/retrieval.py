"""Retrieval for one incident (design 5.3, rule 2; DD21).

Each evidence item asks its own question of the index, together with the incident's description: the
pod's termination, the log's warnings and the running configuration each point at a different section
of a runbook, and one long query made of all of them would blur those together (the embedding model
also reads only the first 512 tokens). A passage scores the best of its matches. Only passages at or
above the relevance threshold are sent to the model; if none is, the answer can only be
insufficient_evidence (app.prompt).

Retrieval is always filtered on the incident's service and its major version, and runs as the
read-only identity, which can see approved, internal passages only.
"""

import os

from app import knowledge

THRESHOLD = float(os.environ.get("ENRICHMENT_RELEVANCE_THRESHOLD", "0.80"))
MAX_PASSAGES = int(os.environ.get("ENRICHMENT_MAX_PASSAGES", "6"))
PER_QUERY = 5
RETRIEVAL_VERSION = f"{knowledge.EMBED_MODEL.split('/')[-1]}|exact|per-evidence-max|t{THRESHOLD:.2f}|k{MAX_PASSAGES}"


def queries(incident: dict, evidence: list[dict]) -> list[str]:
    """The incident's description, then one question per evidence item that is not a gap."""
    description = incident.get("short_description", "")
    asked = [description] if description else []
    for item in evidence:
        if not item["id"].endswith("-GAP"):
            asked.append(f"{description}\n{item['fact']}".strip())
    return asked


def retrieve(conn, embedder, incident: dict, evidence: list[dict], version: str) -> tuple[list[dict], list[dict]]:
    """Returns the passages to send to the model, and every candidate considered with its score."""
    service = incident.get("cmdb_ci", "")
    if not service or not knowledge.major_version(version):
        return [], []
    best: dict[str, dict] = {}
    for question in queries(incident, evidence):
        for row in knowledge.search(conn, embedder.query(question), service, version, limit=PER_QUERY):
            row["score"] = round(float(row["score"]), 3)
            if row["id"] not in best or row["score"] > best[row["id"]]["score"]:
                best[row["id"]] = row
    ranked = sorted(best.values(), key=lambda r: r["score"], reverse=True)
    chosen = [r for r in ranked if r["score"] >= THRESHOLD][:MAX_PASSAGES]
    return chosen, ranked
