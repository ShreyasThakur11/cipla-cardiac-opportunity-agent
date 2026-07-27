"""Citation enforcement.

The case asks for sources in an appendix. That is not a formatting request - it
is the mechanism by which a jury separates what the data shows from what the
analyst read somewhere. So any sentence that makes a claim about the world
outside the supplied dataset has to carry a ``[S-xx]`` marker, and every marker
has to resolve to a real signal in the corpus.

The check is intentionally asymmetric. A missing citation on an external claim
is a warning, not a hard failure: the model is told to add one and moves on. A
citation pointing at a signal that does not exist is a hard failure, because a
fabricated source is worse than no source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..logging_config import get_logger

logger = get_logger(__name__)

_CITATION = re.compile(r"\[(S-\d+)\]")

#: Phrases that signal a claim is about the world rather than about the audit.
#: Deliberately conservative - a false positive costs one unnecessary citation,
#: a false negative lets an unsourced assertion through.
EXTERNAL_CLAIM_MARKERS: tuple[str, ...] = (
    "guideline",
    "guidance",
    "prevalence",
    "epidemiolog",
    "who ",
    "government",
    "policy",
    "regulat",
    "nlem",
    "nppa",
    "price control",
    "patent",
    "approval",
    "trial",
    "study",
    "research",
    "screening",
    "programme",
    "program",
    "air quality",
    "pollution",
    "pm2.5",
    "burden of disease",
    "clinical",
    "published",
    "reported by",
    "association",
    "society",
    "ministry",
    "survey",
)


@dataclass
class CitationReport:
    """Result of checking citations in a draft answer."""

    valid: bool
    cited: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    uncited_claims: list[str] = field(default_factory=list)

    def message(self) -> str:
        parts: list[str] = []
        if self.unknown:
            parts.append(
                f"These citations do not exist in the corpus: {', '.join(self.unknown)}. "
                "Remove them or call retrieve_external_signals to obtain real ones."
            )
        if self.uncited_claims:
            preview = "; ".join(claim[:110] for claim in self.uncited_claims[:3])
            parts.append(
                f"{len(self.uncited_claims)} sentence(s) appear to make an external claim "
                f"without a citation: {preview}"
            )
        return " ".join(parts) or "Citations are complete and all resolve."


def _sentences(text: str) -> list[str]:
    """Split prose into sentences, tolerantly."""
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)
    return [sentence.strip() for sentence in raw if sentence.strip()]


def check_citations(answer: str, known_ids: set[str]) -> CitationReport:
    """Validate citation markers and flag unsourced external claims.

    Args:
        answer: The drafted response.
        known_ids: Signal identifiers present in the corpus.

    Returns:
        A :class:`CitationReport`. ``valid`` is False only when a citation
        points at a signal that does not exist.
    """
    normalised = {identifier.upper() for identifier in known_ids}
    cited = [match.group(1).upper() for match in _CITATION.finditer(answer)]
    unknown = sorted({identifier for identifier in cited if identifier not in normalised})

    uncited: list[str] = []
    for sentence in _sentences(answer):
        lowered = sentence.lower()
        if _CITATION.search(sentence):
            continue
        if any(marker in lowered for marker in EXTERNAL_CLAIM_MARKERS):
            uncited.append(sentence)

    report = CitationReport(
        valid=not unknown,
        cited=sorted(set(cited)),
        unknown=unknown,
        uncited_claims=uncited,
    )
    logger.info(
        "guardrail.citations",
        valid=report.valid,
        cited=len(report.cited),
        unknown=len(unknown),
        uncited_claims=len(uncited),
    )
    return report


__all__ = ["EXTERNAL_CLAIM_MARKERS", "CitationReport", "check_citations"]
