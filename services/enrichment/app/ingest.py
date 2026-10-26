"""Ingests the approved corpus into the knowledge index (phase 05, design 5.6, DD21).

    python -m app.ingest CORPUS_DIR --commit SHA

Runs as the ingestion identity, which owns the index. Every document is loaded with its labels,
including superseded and restricted ones, so the demo can prove that retrieval keeps them out.
A document whose content has not changed is left as it is; one no longer in the corpus is removed.
Prints a JSON summary as its last line, for the build to read.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from app import knowledge

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    doc_id        text PRIMARY KEY,
    title         text NOT NULL,
    content_hash  text NOT NULL,
    source_commit text NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS passages (
    id          text PRIMARY KEY,
    doc_id      text NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    doc_title   text NOT NULL,
    section     text NOT NULL,
    content     text NOT NULL,
    type        text NOT NULL,
    service     text NOT NULL,
    versions    text[] NOT NULL,
    owner       text NOT NULL,
    access      text NOT NULL,
    status      text NOT NULL,
    approved_on date NOT NULL,
    embedding   vector({knowledge.EMBED_DIM}) NOT NULL
);
ALTER TABLE passages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS reader_sees_approved_internal ON passages;
"""


def load_corpus(corpus: Path) -> dict[str, tuple[dict, str, str]]:
    documents: dict[str, tuple[dict, str, str]] = {}
    for path in sorted(corpus.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = knowledge.parse_document(text, path.name)
        if meta["id"] in documents:
            raise knowledge.DocumentError(f"{path.name}: duplicate id {meta['id']}")
        documents[meta["id"]] = (meta, body, knowledge.content_hash(text))
    if not documents:
        raise knowledge.DocumentError(f"no documents in {corpus}")
    return documents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--commit", default="unknown")
    args = parser.parse_args()
    reader = os.environ.get("KNOWLEDGE_READER_ROLE", "knowledge_reader")

    documents = load_corpus(Path(args.corpus))
    embedder = knowledge.embedder()
    summary = {"commit": args.commit, "added": [], "updated": [], "unchanged": [], "removed": []}

    with knowledge.connect() as conn:
        conn.execute(SCHEMA)
        # The reader sees approved, internal passages only, whatever it asks for.
        conn.execute(
            f"CREATE POLICY reader_sees_approved_internal ON passages FOR SELECT TO {reader} "
            "USING (status = 'approved' AND access = 'internal')"
        )
        conn.execute(f"GRANT SELECT ON documents, passages TO {reader}")
        known = dict(conn.execute("SELECT doc_id, content_hash FROM documents").fetchall())

        for doc_id, (meta, body, digest) in documents.items():
            if known.get(doc_id) == digest:
                summary["unchanged"].append(doc_id)
                continue
            passages = knowledge.split_passages(meta, body)
            vectors = embedder.passages([p.text for p in passages])
            conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            conn.execute(
                "INSERT INTO documents (doc_id, title, content_hash, source_commit) VALUES (%s, %s, %s, %s)",
                (doc_id, meta["title"], digest, args.commit),
            )
            for passage, vector in zip(passages, vectors):
                labels = passage.labels
                conn.execute(
                    """INSERT INTO passages (id, doc_id, doc_title, section, content, type, service, versions, owner,
                                             access, status, approved_on, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (passage.id, passage.doc_id, passage.doc_title, passage.section, passage.content, labels["type"],
                     labels["service"], [str(v) for v in labels["versions"]], labels["owner"], labels["access"],
                     labels["status"], labels["approved_on"], vector),
                )
            summary["updated" if doc_id in known else "added"].append(doc_id)

        for doc_id in sorted(set(known) - set(documents)):
            conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            summary["removed"].append(doc_id)

        counts = conn.execute(
            "SELECT count(DISTINCT doc_id), count(*) FROM passages"
        ).fetchone()
        summary["documents"], summary["passages"] = counts
        summary["by_status"] = dict(conn.execute(
            "SELECT status, count(DISTINCT doc_id) FROM passages GROUP BY status").fetchall())
        summary["by_access"] = dict(conn.execute(
            "SELECT access, count(DISTINCT doc_id) FROM passages GROUP BY access").fetchall())

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except knowledge.DocumentError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
