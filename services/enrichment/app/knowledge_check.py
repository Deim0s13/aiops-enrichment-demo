"""Checks the knowledge index as the enrichment service will use it (phase 05).

    python -m app.knowledge_check

Runs as the read-only identity. Asks the question the memory fault's evidence poses, for
payments-notify 2.4.1 and without the service's name, as the service asks it, and reports what the
service would get back (skipping the same navigation sections), what it can see at all, and whether
it can change anything. Also asks a question no document answers, and reports its scores only, to
calibrate the service's relevance threshold. Prints a JSON report as its last line; the build judges
it.
"""

import json
import os

import psycopg

from app import knowledge, retrieval

QUERY = os.environ.get(
    "KNOWLEDGE_CHECK_QUERY",
    "container OOMKilled exit code 137, heap well short of its maximum, maximum heap equal to "
    "the container memory limit, NotificationTemplateCache growing and entries are never evicted",
)
# A question no document answers (scenario S2, provider throttling), asked only to report how close an
# unanswered question scores: the gap between the two sets the relevance threshold (M4.7).
CALIBRATION_QUERY = os.environ.get(
    "KNOWLEDGE_CALIBRATION_QUERY",
    "HTTP 429 Too Many Requests from MessageHub, rate limit exceeded, notification delivery retried "
    "with back-off, customer confirmations delayed",
)
# Each scenario's incident description, as its alert states it and without the service's name: how
# close each comes to the knowledge base on its own, reported only (DD26).
DESCRIPTIONS = {
    "memory": "was terminated for exceeding its memory limit (OOMKilled) and restarted",
    "throttling": "customer confirmations are queuing: MessageHub is refusing deliveries",
}
SERVICE = os.environ.get("KNOWLEDGE_CHECK_SERVICE", "payments-notify")
VERSION = os.environ.get("KNOWLEDGE_CHECK_VERSION", "2.4.1")


def main() -> None:
    report: dict = {}
    with knowledge.connect() as conn:
        embedder = knowledge.embedder()
        results = knowledge.search(conn, embedder.query(QUERY), SERVICE, VERSION, limit=5,
                                   skip_sections=retrieval.SKIP_SECTIONS)
        report["results"] = [{"id": r["id"], "score": round(float(r["score"]), 3)} for r in results]
        calibration = knowledge.search(conn, embedder.query(CALIBRATION_QUERY), SERVICE, VERSION, limit=3,
                                       skip_sections=retrieval.SKIP_SECTIONS)
        report["calibration"] = [{"id": r["id"], "score": round(float(r["score"]), 3)} for r in calibration]
        # The service's own document gate (DD27), on each scenario's description: the best documents and
        # their scores, and which pass.
        report["descriptions"] = {}
        for name, text in DESCRIPTIONS.items():
            verdict = retrieval.gate(conn, embedder, {"cmdb_ci": SERVICE, "short_description": text}, VERSION)
            top = sorted(verdict["documents"].items(), key=lambda kv: kv[1], reverse=True)[:3]
            report["descriptions"][name] = {"score": top[0][1] if top else 0, "top": top, "passed": verdict["passed"]}
        report["document_gate"] = retrieval.DOCUMENT_GATE
        # What this identity can see at all, with no filter in the query: the database decides.
        report["visible"] = dict(conn.execute(
            "SELECT status || '/' || access, count(*) FROM passages GROUP BY 1").fetchall())
        report["visible_documents"] = [row[0] for row in conn.execute(
            "SELECT DISTINCT doc_id FROM passages ORDER BY 1").fetchall()]
        try:
            conn.execute("DELETE FROM passages WHERE doc_id = 'KB-RB-014'")
            report["can_write"] = True
        except psycopg.Error as error:
            report["can_write"] = False
            report["write_refused"] = type(error).__name__
        conn.rollback()
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
