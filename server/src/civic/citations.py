"""Citation marker validation (ADR-005 control 3).

Mechanical check that generated [n] markers point at sources we actually
provided. Out-of-range markers are removed; an answer whose markers are all
removed fails grounding and triggers the refusal path upstream.
"""

import re

MARKER_RE = re.compile(r"\[(\d{1,2})\]")


def validate(text: str, n_sources: int) -> tuple[str, list[int]]:
    """Return (cleaned_text, used_source_numbers_sorted).

    Markers outside 1..n_sources are stripped entirely (including stray
    brackets left over from fabrication attempts like [12] against 8 sources).
    """
    used: set[int] = set()

    def repl(match: re.Match[str]) -> str:
        num = int(match.group(1))
        if 1 <= num <= n_sources:
            used.add(num)
            return match.group(0)
        return ""

    cleaned = MARKER_RE.sub(repl, text)
    cleaned = re.sub(r"\s+([.,;:!?)])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"^\s+", "", cleaned)
    return cleaned, sorted(used)
