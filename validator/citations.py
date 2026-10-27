"""Drop any model sentence that does not cite real evidence.

The model writes prose; this module decides what survives. A sentence that cites
nothing, or cites an id we never emitted, is removed rather than rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contracts.contracts import Evidence, ExplanationSentence

EV_REF = re.compile(r"\[?(EV-\d{1,4})\]?")
MAX_SENTENCE_LEN = 400


@dataclass(frozen=True)
class CitationResult:
    kept: list[ExplanationSentence]
    dropped: int
    dropped_reasons: list[str]


def extract_ids(text: str) -> list[str]:
    """Every EV-n mentioned in a sentence, in order, without duplicates."""
    seen: list[str] = []
    for match in EV_REF.finditer(text):
        ref = match.group(1)
        if ref not in seen:
            seen.append(ref)
    return seen


def validate(
    sentences: list[ExplanationSentence] | list[str], evidence: list[Evidence]
) -> CitationResult:
    """Keep only sentences whose citations all exist in `evidence`."""
    known = {e.id for e in evidence}
    kept: list[ExplanationSentence] = []
    reasons: list[str] = []

    for item in sentences:
        text = item.text if isinstance(item, ExplanationSentence) else str(item)
        text = text.strip()
        if not text:
            reasons.append("empty sentence")
            continue
        if len(text) > MAX_SENTENCE_LEN:
            reasons.append(f"sentence over {MAX_SENTENCE_LEN} chars")
            continue

        cited = extract_ids(text)
        if not cited:
            reasons.append(f"no citation: {text[:60]!r}")
            continue
        unknown = [ref for ref in cited if ref not in known]
        if unknown:
            reasons.append(f"cites unknown evidence {unknown}: {text[:60]!r}")
            continue

        kept.append(ExplanationSentence(text=text, evidence_ids=cited))

    return CitationResult(kept=kept, dropped=len(sentences) - len(kept), dropped_reasons=reasons)
