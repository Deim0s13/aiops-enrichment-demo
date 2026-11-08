#!/usr/bin/env python3
"""Checks knowledge documents against the corpus rules and, for resolutions, the template (DD33).

Runs on every pull request that changes knowledge/ (.github/workflows/knowledge.yml), so a document
that does not follow the template cannot be merged, whoever wrote it, and in phase 06 on the
service's drafted resolution. Usage: check.py [FILE ...]; with no files, checks the whole corpus.
Exits non-zero, listing every problem, if any document fails.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "knowledge"
TEMPLATE = Path(__file__).resolve().parent / "resolution-template.md"
REQUIRED = ("id", "title", "type", "service", "versions", "owner", "access", "status", "approved_on")
CHOICES = {"type": ("runbook", "resolution"), "access": ("internal", "restricted"),
           "status": ("approved", "superseded", "draft")}
OPTIONAL_SECTIONS = ("Background",)


def split(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        raise ValueError("no metadata header between --- lines")
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("the metadata header is not a set of fields")
    return meta, match.group(2)


def headings(body: str) -> list[str]:
    return [re.sub(r"\s*\(.*\)$", "", h.strip()) for h in re.findall(r"^## (.+)$", body, re.M)]


def template_sections() -> list[str]:
    return [h for h in headings(split(TEMPLATE.read_text())[1]) if h not in OPTIONAL_SECTIONS]


def check(path: Path, required_sections: list[str]) -> list[str]:
    try:
        meta, body = split(path.read_text())
    except (ValueError, yaml.YAMLError) as error:
        return [f"{path.name}: {error}"]
    problems = [f"{path.name}: no {key} in the metadata" for key in REQUIRED if not meta.get(key)]
    for key, allowed in CHOICES.items():
        if meta.get(key) and meta[key] not in allowed:
            problems.append(f"{path.name}: {key} is {meta[key]!r}, not one of {', '.join(allowed)}")
    if meta.get("id") and not path.name.startswith(f"{meta['id']}-") and path.stem != meta["id"]:
        problems.append(f"{path.name}: the file name does not start with its id, {meta['id']}")
    if meta.get("versions") is not None and not isinstance(meta.get("versions"), list):
        problems.append(f"{path.name}: versions is not a list")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(meta.get("approved_on", ""))):
        problems.append(f"{path.name}: approved_on is not a date (YYYY-MM-DD)")
    if not re.search(rf"^# {re.escape(str(meta.get('title', '')))}$", body, re.M):
        problems.append(f"{path.name}: the first heading is not the title")
    if meta.get("type") == "resolution":
        if not str(meta.get("title", "")).startswith("Resolution: INC"):
            problems.append(f"{path.name}: a resolution's title starts \"Resolution: INC\" and the incident number")
        found = [h for h in headings(body) if h not in OPTIONAL_SECTIONS]
        if found != required_sections:
            problems.append(f"{path.name}: its sections are {', '.join(found) or 'none'}; the template's are "
                            f"{', '.join(required_sections)}, in that order (Background is optional)")
        for section in required_sections:
            text = re.search(rf"^## {re.escape(section)}[^\n]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
            if text and not text.group(1).strip():
                problems.append(f"{path.name}: {section} is empty")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(p for p in CORPUS.rglob("*.md") if p.name.lower() != "readme.md")
    sections = template_sections()
    problems, ids = [], {}
    for path in paths:
        problems += check(path, sections)
    for path in sorted(p for p in CORPUS.rglob("*.md") if p.name.lower() != "readme.md") + [
            p for p in paths if CORPUS not in p.resolve().parents]:
        try:
            ids.setdefault(split(path.read_text())[0].get("id"), set()).add(path.resolve())
        except (ValueError, yaml.YAMLError):
            pass
    problems += [f"id {i} is used by {', '.join(sorted(p.name for p in ps))}" for i, ps in ids.items() if i and len(ps) > 1]
    for problem in problems:
        print(problem)
    print(f"{len(paths)} document(s) checked; {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
