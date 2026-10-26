"""The knowledge index (design 5.6, DD21): documents, passages, embeddings and filtered search.

Shared by the ingestion job (app.ingest), the build's check (app.knowledge_check) and, from M4, the
enrichment service. Documents are Markdown with a YAML metadata header. Each section becomes a
passage, with the document's labels, so retrieval can filter on them before ranking.

The database enforces the access rules itself: the reader identity the service uses can see only
approved, internal passages (row-level security), so a superseded or restricted document cannot
reach the model even if a query forgets a filter.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field

import yaml

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
MODEL_DIR = os.environ.get("KNOWLEDGE_MODEL_DIR", "/opt/app-root/models")

REQUIRED = ("id", "title", "type", "service", "versions", "owner", "access", "status", "approved_on")
STATUSES = ("approved", "superseded", "draft")
ACCESS = ("internal", "restricted")
TYPES = ("runbook", "resolution")


@dataclass
class Passage:
    id: str
    doc_id: str
    doc_title: str
    section: str
    content: str
    labels: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """What is embedded and what the model reads: the passage, with enough context to stand alone."""
        return f"{self.doc_id} {self.doc_title}\nSection: {self.section}\n\n{self.content}"


class DocumentError(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_document(text: str, name: str = "") -> tuple[dict, str]:
    """Split a document into its metadata and its body, and check the metadata."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        raise DocumentError(f"{name}: no metadata header")
    meta = yaml.safe_load(match.group(1)) or {}
    missing = [key for key in REQUIRED if not meta.get(key)]
    if missing:
        raise DocumentError(f"{name}: missing {', '.join(missing)}")
    if meta["status"] not in STATUSES or meta["access"] not in ACCESS or meta["type"] not in TYPES:
        raise DocumentError(f"{name}: status, access or type is not one of the allowed values")
    if not isinstance(meta["versions"], list) or not all(re.fullmatch(r"\d+\.x", str(v)) for v in meta["versions"]):
        raise DocumentError(f"{name}: versions must be a list such as [\"2.x\"]")
    meta["approved_on"] = str(meta["approved_on"])
    return meta, match.group(2)


def split_passages(meta: dict, body: str) -> list[Passage]:
    """One passage per section. A section with subsections becomes one passage per subsection,
    so "Actions, Level 1" and "Actions, Level 2" can be cited separately."""
    labels = {key: meta[key] for key in ("type", "service", "versions", "owner", "access", "status", "approved_on")}
    passages: list[Passage] = []
    sections = re.split(r"^## +", body, flags=re.M)
    for section in sections[1:]:
        heading, _, content = section.partition("\n")
        heading = heading.strip()
        parts = re.split(r"^### +", content, flags=re.M)
        if len(parts) == 1:
            pieces = [(heading, heading, content)]
        else:
            intro = parts[0].strip()
            pieces = []
            for part in parts[1:]:
                sub, _, sub_content = part.partition("\n")
                # The ID uses the subsection's short name ("Level 1"), so citations stay readable.
                pieces.append((f"{heading}, {sub.strip()}", f"{heading} {sub.split(':')[0]}",
                               (intro + "\n\n" if intro else "") + sub_content))
        for title, key, text in pieces:
            text = text.strip()
            if text:
                passages.append(Passage(id=f"{meta['id']}#{slug(key)}", doc_id=meta["id"], doc_title=meta["title"],
                                        section=title, content=text, labels=labels))
    return passages


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def major_version(version: str) -> str:
    """The version label documents carry: 2.4.1 is covered by documents for 2.x."""
    match = re.match(r"^(\d+)", version or "")
    return f"{match.group(1)}.x" if match else ""


class Embedder:
    """BGE small, run on CPU in the process. The model is baked into the image at build time and
    loaded from disk only, so nothing is downloaded while the service runs."""

    def __init__(self):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(EMBED_MODEL, cache_dir=MODEL_DIR, local_files_only=True)

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.passage_embed(texts)]

    def query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self.model.query_embed(text)))]


class TestEmbedder:
    """For tests away from the cluster only, where the model cannot be downloaded: a bag of hashed
    words, so documents that share words with a query rank higher. Never used in the cluster."""

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * EMBED_DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
        norm = sum(x * x for x in vector) ** 0.5 or 1.0
        return [x / norm for x in vector]

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vector(text)


def embedder():
    return TestEmbedder() if os.environ.get("KNOWLEDGE_TEST_EMBEDDER") == "1" else Embedder()


def connect():
    """Connects with the identity in the environment: KNOWLEDGE_DB_HOST, _PORT, _NAME, _USER and
    _PASSWORD. TLS is verified against OpenShift's service CA when KNOWLEDGE_DB_SSLROOTCERT is set."""
    import psycopg
    from pgvector.psycopg import register_vector

    root_cert = os.environ.get("KNOWLEDGE_DB_SSLROOTCERT", "")
    conn = psycopg.connect(
        host=os.environ["KNOWLEDGE_DB_HOST"],
        port=int(os.environ.get("KNOWLEDGE_DB_PORT", "5432")),
        dbname=os.environ.get("KNOWLEDGE_DB_NAME", "knowledge"),
        user=os.environ["KNOWLEDGE_DB_USER"],
        password=os.environ["KNOWLEDGE_DB_PASSWORD"],
        sslmode=os.environ.get("KNOWLEDGE_DB_SSLMODE", "verify-full" if root_cert else "require"),
        sslrootcert=root_cert or None,
        connect_timeout=10,
    )
    register_vector(conn)
    return conn


def search(conn, query_vector, service: str, version: str, limit: int = 5) -> list[dict]:
    """The passages closest to the query, for one service and its version only (design 5.3, rule
    2). Status and access are enforced by the database for the reader identity, and repeated here
    so the query is correct for any identity. Exact search: the corpus is small, and an exact
    scan never misses a passage that a filter would otherwise starve an approximate index of."""
    import numpy as np

    rows = conn.execute(
        """
        SELECT id, doc_id, doc_title, section, content, 1 - (embedding <=> %(q)s) AS score
        FROM passages
        WHERE service = %(service)s AND %(version)s = ANY(versions)
          AND status = 'approved' AND access = 'internal'
        ORDER BY embedding <=> %(q)s
        LIMIT %(limit)s
        """,
        {"q": np.array(query_vector), "service": service, "version": major_version(version), "limit": limit},
    ).fetchall()
    keys = ("id", "doc_id", "doc_title", "section", "content", "score")
    return [dict(zip(keys, row)) for row in rows]
