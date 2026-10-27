"""Sanitisation (design 5.3, rule 1): redacts secrets and personal data from evidence on arrival.

Evidence is collected from logs, configuration and events, which can carry things that must never
reach a prompt, a trace or a work note: tokens, keys, passwords, email addresses and card numbers.
Each is replaced with a labelled placeholder, such as [REDACTED:card], and counted, so the note can
say that something was removed without saying what.

The same function runs over the model's answer before it is returned, in case the model writes
something that looks like one of these. Patterns are deliberately broad: a false positive costs a
few characters of evidence, a false negative puts a secret into ServiceNow.
"""

import re
from collections import Counter

# Order matters: whole blocks first, then specific token formats, then generic key=value pairs.
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED:private_key]"),
    ("token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED:token]"),
    ("token", re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED:token]"),
    ("key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED:key]"),
    ("key", re.compile(r"\b(sk|rk|pk)-[A-Za-z0-9_-]{20,}"), "[REDACTED:key]"),
    ("key", re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}"), "[REDACTED:key]"),
    ("secret", re.compile(
        r"(?i)\b(password|passwd|pwd|secret|client[_-]?secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key)"
        r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"), r"\1\2[REDACTED:secret]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED:email]"),
]

# Runs of 14 to 19 digits, optionally grouped by spaces or hyphens. Only those that pass the Luhn
# check are treated as card numbers, so most identifiers and counters are left alone.
_CARD_LIKE = re.compile(r"(?<![\d-])(?:\d[ -]?){13,18}\d(?![\d-])")


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def sanitise(text: str, counts: Counter | None = None) -> str:
    """Returns the text with every match replaced, adding what was removed to counts."""
    if not text:
        return text
    counts = counts if counts is not None else Counter()
    for kind, pattern, replacement in _PATTERNS:
        text, found = pattern.subn(replacement, text)
        if found:
            counts[kind] += found

    def card(match: re.Match) -> str:
        digits = re.sub(r"[ -]", "", match.group(0))
        if 14 <= len(digits) <= 19 and _luhn(digits):
            counts["card"] += 1
            return "[REDACTED:card]"
        return match.group(0)

    return _CARD_LIKE.sub(card, text)


def sanitise_tree(value, counts: Counter):
    """Sanitises every string in a structure of dicts and lists, such as the model's answer."""
    if isinstance(value, str):
        return sanitise(value, counts)
    if isinstance(value, list):
        return [sanitise_tree(v, counts) for v in value]
    if isinstance(value, dict):
        return {k: sanitise_tree(v, counts) for k, v in value.items()}
    return value
