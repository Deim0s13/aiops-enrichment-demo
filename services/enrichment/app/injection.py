"""Text addressed to an AI assistant, found in evidence or in fetched documentation (DD30).

Evidence is data, and the prompt says so, but a model may still be swayed, and an engineer reading
the note should know that something in the evidence tried. So the service looks for the usual shapes
of a prompt injection itself, rather than relying on the model to mention it: in evidence, the item
is kept (it is what the service observed) and the note says what was found; in fetched
documentation, the section is not used at all, because a vendor page has no business addressing an
assistant.

The patterns are deliberately narrow: a false positive puts a puzzling line in the note, and the
schema and the policy, not this check, are what stop an injected instruction taking effect.
"""

import re

_PATTERNS = [
    re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|your|any)\b"
               r"[^.\n]{0,20}\b(instructions?|rules|prompts?|guidance)\b", re.I),
    re.compile(r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(assistant|ai|model|llm|chatbot|copilot)\b", re.I),
    re.compile(r"\b(system|developer)\s+prompt\b", re.I),
    re.compile(r"\byou are (now )?(an?|the) (ai|assistant|language model|model)\b", re.I),
    re.compile(r"\b(state|say|claim|report) that no (manual )?review\b", re.I),
]


def find(text: str) -> str | None:
    """A short excerpt around the first match, or None."""
    for pattern in _PATTERNS:
        match = pattern.search(text or "")
        if match:
            excerpt = " ".join(text[match.start():match.end() + 60].split())
            if len(excerpt) > 80:
                excerpt = excerpt[:80].rsplit(" ", 1)[0] + "..."
            return excerpt
    return None
