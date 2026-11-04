"""Research in vendor documentation (DD29).

When no approved runbook or resolution covers an incident's failure, there is no documented fix, and
until now the model could offer only its own ideas. An engineer in that position reads the vendor's
documentation. This module does the same, under rules a risk team can read:

- Only sources on an allow-list, set per service by the build from the inventory, are researched, and
  only when the evidence names the dependency the source documents (MessageHub in a 429 log line).
- Every page comes from the source's own site: its sitemap is read, and a page on any other host, or
  a redirect to one, is refused. Pages are fetched over verified TLS, size-limited and cached for a
  few minutes.
- Pages are split into sections, sanitised like evidence, and ranked against the incident's description
  and the evidence that names the dependency, with the same embedding model as the approved knowledge.
  The best few, at or above a floor, go to the model as RESEARCH, each with its page, section, address
  and the date the page says it was updated.
- A section with text addressed to an AI assistant is not used at all (app.injection).
- Nothing about the incident leaves the cluster: the service only reads the documentation, so no query
  is sent anywhere. A source that cannot be reached is a gap, not a failure.

What the model makes of it is a researched fix: a suggestion that cites the documentation it rests on.
It is not approved by ACME, never carries a job, and always requires manual review (app.policy).
"""

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser

from app import injection
from app.sanitise import sanitise

ENABLED = os.environ.get("ENRICHMENT_RESEARCH", "on") == "on"
# [{"id": "messagehub", "name": "MessageHub", "services": ["payments-notify"], "match": ["MessageHub"],
#   "sitemap": "https://.../sitemap.xml"}], from the inventory (demo_research_sources).
SOURCES = json.loads(os.environ.get("ENRICHMENT_RESEARCH_SOURCES", "") or "[]")
THRESHOLD = float(os.environ.get("ENRICHMENT_RESEARCH_THRESHOLD", "0.60"))
MAX_SECTIONS = int(os.environ.get("ENRICHMENT_RESEARCH_MAX_SECTIONS", "6"))
# At most this many sections from one page, so one page cannot crowd out the others (DD32): the first
# researched S2 note missed MessageHub's status page and who may ask for a higher limit.
PER_PAGE = int(os.environ.get("ENRICHMENT_RESEARCH_PER_PAGE", "2"))
MAX_PAGES = int(os.environ.get("ENRICHMENT_RESEARCH_MAX_PAGES", "12"))
PAGE_BYTES = 262144
TIMEOUT = float(os.environ.get("ENRICHMENT_RESEARCH_TIMEOUT", "5"))
CACHE_SECONDS = int(os.environ.get("ENRICHMENT_RESEARCH_CACHE_SECONDS", "900"))
CA_FILE = os.environ.get("ENRICHMENT_RESEARCH_CA_FILE", "")
RESEARCH_VERSION = (f"allow-list|named-in-evidence|sitemap|h2-sections|no-home-page|t{THRESHOLD:.2f}|k{MAX_SECTIONS}"
                    f"|page{PER_PAGE}")

_cache: dict[str, tuple[float, list[dict], list[str]]] = {}


class ResearchError(RuntimeError):
    pass


def sources_for(incident: dict, evidence: list[dict]) -> list[dict]:
    """The allow-listed sources for the incident's service whose dependency the evidence names, each
    with the IDs of the evidence that names it."""
    if not ENABLED:
        return []
    found = []
    for source in SOURCES:
        if incident.get("cmdb_ci") not in source.get("services", []) or not source.get("sitemap"):
            continue
        terms = [re.compile(rf"\b{re.escape(t)}\b", re.I) for t in source.get("match") or [source.get("name", "")] if t]
        named = [e["id"] for e in evidence if not e["id"].endswith("-GAP") and any(t.search(e["fact"]) for t in terms)]
        if named or any(t.search(incident.get("short_description", "")) for t in terms):
            found.append({**source, "named_in": named})
    return found


class _NoOffSiteRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != self.host:
            raise ResearchError(f"a page redirected off the source's site ({urllib.parse.urlsplit(newurl).netloc})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str, host: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc != host:
        raise ResearchError(f"{url} is not on the source's site")
    context = ssl.create_default_context(cafile=CA_FILE or None)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), _NoOffSiteRedirect(host))
    request = urllib.request.Request(url, headers={"User-Agent": "acme-enrichment-research/1"})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body = response.read(PAGE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise ResearchError(f"{url} answered HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ResearchError(f"{parts.netloc} could not be reached ({type(getattr(error, 'reason', error)).__name__})") from None
    if len(body) > PAGE_BYTES:
        raise ResearchError(f"{url} is larger than {PAGE_BYTES // 1024} KiB")
    return body.decode("utf-8", errors="replace")


class _Page(HTMLParser):
    """Splits a documentation page into its title, its last-updated date and its h2 sections."""

    SKIP = {"script", "style", "nav", "header", "footer"}

    def __init__(self):
        super().__init__()
        self.title, self.updated, self.sections = "", "", []
        self._skip, self._in, self._section_id, self._link = 0, "", "", False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "meta" and attrs.get("name") == "last-updated":
            self.updated = attrs.get("content", "")[:30]
        elif tag == "section" and attrs.get("id"):
            self._section_id = attrs["id"]
        elif tag == "a":
            self._link = True
        elif tag in ("p", "li", "br", "tr") and self.sections and not self._skip:
            self.sections[-1]["text"] += " "
        elif tag in ("h1", "h2") and not self._skip:
            self._in = tag
            if tag == "h2":
                self.sections.append({"id": attrs.get("id") or self._section_id, "heading": "", "text": ""})

    def handle_endtag(self, tag):
        if tag == "a":
            self._link = False
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == self._in:
            self._in = ""

    def handle_data(self, data):
        if self._skip:
            return
        if self._in == "h1":
            self.title += data
        elif self._in == "h2" and self.sections:
            self.sections[-1]["heading"] += data
        elif self.sections:
            self.sections[-1]["text"] += data
            if self._link:
                self.sections[-1]["links"] = self.sections[-1].get("links", 0) + len(data.strip())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "section"


def _site(source: dict, embedder, counts: Counter) -> tuple[list[dict], list[str]]:
    """Every usable section of the source's pages, embedded, and notes on any section not used, from the
    cache if it is fresh."""
    cached = _cache.get(source["id"])
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1], cached[2]
    notes: list[str] = []
    host = urllib.parse.urlsplit(source["sitemap"]).netloc
    sitemap = _fetch(source["sitemap"], host)
    urls = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap)
            if urllib.parse.urlsplit(u).netloc == host][:MAX_PAGES]
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sections = []
    for url in urls:
        # A site's home page is a contents list: it says nothing to act on, and took a slot from pages that do.
        if re.search(r"/(index\.html?)?$", urllib.parse.urlsplit(url).path or "/"):
            continue
        parser = _Page()
        parser.feed(_fetch(url, host))
        page = re.sub(r"\.html?$", "", urllib.parse.urlsplit(url).path.strip("/").split("/")[-1]) or "index"
        for section in parser.sections:
            text = " ".join(section["text"].split())
            heading = " ".join(section["heading"].split())
            if not text:
                continue
            found = injection.find(f"{heading} {text}")
            if found:
                notes.append(f"A section of {source['name']}'s documentation ({url}, {heading}) contains text addressed to "
                             f"an AI assistant (\"{found}\"), so it was not used.")
                continue
            sections.append({"id": f"RD-{source['id']}-{_slug(page)}#{section['id'] or _slug(heading)}",
                             "source": source["name"], "title": " ".join(parser.title.split()) or page, "section": heading,
                             "url": f"{url}#{section['id']}" if section["id"] else url, "updated": parser.updated,
                             "fetched_at": fetched_at, "content": sanitise(text, counts)[:1500]})
    if sections:
        for section, vector in zip(sections, embedder.passages([f"{s['title']}: {s['section']}\n{s['content']}"
                                                                for s in sections])):
            section["vector"] = vector
    _cache[source["id"]] = (time.time(), sections, notes)
    return sections, notes


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


def research(embedder, incident: dict, evidence: list[dict], sources: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Returns the sections to send to the model, every section considered with its score, and notes for
    the gaps: a source that could not be reached, or a section that was not used."""
    notes: list[str] = []
    counts: Counter = Counter()
    candidates: list[dict] = []
    description = incident.get("short_description", "")
    for source in sources:
        try:
            sections, dropped = _site(source, embedder, counts)
            notes += dropped
        except ResearchError as error:
            notes.append(f"{source['name']}'s documentation could not be researched: {error}.")
            continue
        named = [e for e in evidence if e["id"] in source["named_in"]]
        questions = [description] + [f"{description}\n{e['fact']}" for e in named]
        vectors = [embedder.query(q) for q in questions if q.strip()]
        for section in sections:
            score = max((_cosine(v, section["vector"]) for v in vectors), default=0.0)
            candidates.append({**{k: v for k, v in section.items() if k != "vector"}, "score": round(score, 3)})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    chosen, per_page = [], {}
    for candidate in candidates:
        page = candidate["id"].split("#")[0]
        if candidate["score"] >= THRESHOLD and per_page.get(page, 0) < PER_PAGE and len(chosen) < MAX_SECTIONS:
            chosen.append(candidate)
            per_page[page] = per_page.get(page, 0) + 1
    if sources and not chosen and not notes:
        notes.append(f"No section of {', '.join(s['name'] for s in sources)}'s documentation met the research floor of "
                     f"{THRESHOLD:.2f}.")
    return chosen, candidates, notes
