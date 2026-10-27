"""Retrieval for one incident (design 5.3, rule 2; DD21, DD24).

Each evidence item asks its own question of the index, together with the incident's description: the
pod's termination, the log's warnings and the running configuration each point at a different section
of a runbook, and one long query made of all of them would blur those together (the embedding model
also reads only the first 512 tokens). A passage scores the best of its matches.

Sections that describe a document rather than say what to do (its Purpose, Scope, Related documents,
Change history and Timeline) are not searched: they are short and mention every keyword, so they
outranked the runbook's Diagnosis and Actions in the first cluster runs, and the model was left
without the documented fix. Instead, when a document's passages are chosen, its actionable sections
come with them: a runbook's Diagnosis and Actions, a resolution's Resolution and Root cause. A
runbook is meant to be followed, not sampled.

Only passages at or above the relevance threshold are chosen; if none is, there is no documented fix
and the answer can only be insufficient_evidence (app.prompt). Retrieval is always filtered on the
incident's service and its major version, and runs as the read-only identity, which can see
approved, internal passages only.
"""

import os

from app import knowledge

THRESHOLD = float(os.environ.get("ENRICHMENT_RELEVANCE_THRESHOLD", "0.80"))
MAX_PASSAGES = int(os.environ.get("ENRICHMENT_MAX_PASSAGES", "5"))
EXPAND_DOCUMENTS = int(os.environ.get("ENRICHMENT_EXPAND_DOCUMENTS", "2"))
SKIP_SECTIONS = tuple(s.strip() for s in os.environ.get(
    "ENRICHMENT_SKIP_SECTIONS", "Purpose,Scope,Related documents,Change history,Timeline").split(",") if s.strip())
# The sections that say what to do, by document type, in the order the model should read them.
ACTIONABLE = {"runbook": ("Diagnosis", "Actions"), "resolution": ("Root cause", "Resolution")}
PER_QUERY = 5
RETRIEVAL_VERSION = (f"{knowledge.EMBED_MODEL.split('/')[-1]}|exact|per-evidence-max|skip-navigation|"
                     f"expand{EXPAND_DOCUMENTS}|t{THRESHOLD:.2f}|k{MAX_PASSAGES}")


def queries(incident: dict, evidence: list[dict]) -> list[str]:
    """The incident's description, then one question per evidence item that is not a gap."""
    description = incident.get("short_description", "")
    asked = [description] if description else []
    for item in evidence:
        if not item["id"].endswith("-GAP"):
            asked.append(f"{description}\n{item['fact']}".strip())
    return asked


def retrieve(conn, embedder, incident: dict, evidence: list[dict], version: str) -> tuple[list[dict], list[dict]]:
    """Returns the passages to send to the model, and every candidate considered with its score. A
    passage added with its document carries added_with: the ID of the passage that matched."""
    service = incident.get("cmdb_ci", "")
    if not service or not knowledge.major_version(version):
        return [], []
    best: dict[str, dict] = {}
    for question in queries(incident, evidence):
        for row in knowledge.search(conn, embedder.query(question), service, version, limit=PER_QUERY,
                                    skip_sections=SKIP_SECTIONS):
            row["score"] = round(float(row["score"]), 3)
            if row["id"] not in best or row["score"] > best[row["id"]]["score"]:
                best[row["id"]] = row
    ranked = sorted(best.values(), key=lambda r: r["score"], reverse=True)
    chosen = [dict(r, added_with=None) for r in ranked if r["score"] >= THRESHOLD][:MAX_PASSAGES]

    # The best-matching documents bring their actionable sections, if not already chosen.
    have = {p["id"] for p in chosen}
    documents: list[dict] = []
    for passage in chosen:
        if passage["doc_id"] not in {d["doc_id"] for d in documents}:
            documents.append(passage)
    for top in documents[:EXPAND_DOCUMENTS]:
        for extra in knowledge.sections(conn, top["doc_id"], ACTIONABLE.get(top["type"], ())):
            if extra["id"] not in have:
                have.add(extra["id"])
                chosen.append(dict(extra, score=best.get(extra["id"], {}).get("score"), added_with=top["id"]))
    return chosen, ranked
