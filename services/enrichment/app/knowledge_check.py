"""Checks the knowledge index as the enrichment service will use it (phase 05).

    python -m app.knowledge_check

Runs as the read-only identity. Asks the question the memory fault's evidence poses, for
payments-notify 2.4.1, and reports what the service would get back, what it can see at all, and
whether it can change anything. Also asks a question no document answers, and reports its scores
only, to calibrate the service's relevance threshold. Prints a JSON report as its last line; the build judges it.
"""

import json
import os

import psycopg

from app import knowledge

QUERY = os.environ.get(
    "KNOWLEDGE_CHECK_QUERY",
    "payments-notify container OOMKilled exit code 137, heap well short of its maximum, maximum heap equal to "
    "the container memory limit, NotificationTemplateCache growing and entries are never evicted",
)
# A question no document answers (scenario S2, provider throttling), asked only to report how close an
# unanswered question scores: the gap between the two sets the relevance threshold (M4.7).
CALIBRATION_QUERY = os.environ.get(
    "KNOWLEDGE_CALIBRATION_QUERY",
    "payments-notify HTTP 429 Too Many Requests from MessageHub, rate limit exceeded, notification delivery retried "
    "with back-off, customer confirmations delayed",
)
SERVICE = os.environ.get("KNOWLEDGE_CHECK_SERVICE", "payments-notify")
VERSION = os.environ.get("KNOWLEDGE_CHECK_VERSION", "2.4.1")


def main() -> None:
    report: dict = {}
    with knowledge.connect() as conn:
        embedder = knowledge.embedder()
        results = knowledge.search(conn, embedder.query(QUERY), SERVICE, VERSION, limit=5)
        report["results"] = [{"id": r["id"], "score": round(float(r["score"]), 3)} for r in results]
        calibration = knowledge.search(conn, embedder.query(CALIBRATION_QUERY), SERVICE, VERSION, limit=3)
        report["calibration"] = [{"id": r["id"], "score": round(float(r["score"]), 3)} for r in calibration]
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
