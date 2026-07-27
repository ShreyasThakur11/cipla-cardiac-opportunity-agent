"""Prompt-injection defence on retrieved content.

Everything the agent reads through a tool is data, not instruction. The signal
corpus in this repository is trusted - we wrote it - but the boundary has to be
enforced at the code level rather than assumed, for two concrete reasons:

* The corpus is designed to be extended. The moment somebody drops in a
  competitor's press release or a scraped guideline page, untrusted text is
  flowing into the model's context.
* ``sql_query`` returns free text from the warehouse - brand names, company
  names, pack descriptions. Those originate outside our control.

So retrieved text is scanned for instruction-shaped content, neutralised if
found, and wrapped in an explicit data envelope that tells the model what it is
looking at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..logging_config import get_logger

logger = get_logger(__name__)

#: Patterns that look like an instruction aimed at the model rather than prose.
INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (?:all |any |the )?(?:previous|prior|above|preceding) instructions", re.I),
    re.compile(r"disregard (?:the |your )?(?:system prompt|instructions|rules|guardrails)", re.I),
    re.compile(r"you are now (?:a|an|the)\b", re.I),
    re.compile(r"new (?:system )?instructions?\s*:", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"^\s*(?:system|assistant)\s*:", re.I | re.MULTILINE),
    re.compile(r"reveal (?:your |the )?(?:system prompt|instructions|api key)", re.I),
    re.compile(r"do not (?:cite|mention|tell)", re.I),
    re.compile(r"\b(?:override|bypass) (?:the )?(?:guardrail|safety|verification)", re.I),
)

_ENVELOPE_OPEN = "<retrieved_data source={source!r}>"
_ENVELOPE_CLOSE = "</retrieved_data>"


@dataclass
class InjectionReport:
    """What a scan found."""

    clean: bool
    matches: list[str] = field(default_factory=list)
    source: str = ""


def scan_for_injection(text: str, source: str = "") -> InjectionReport:
    """Look for instruction-shaped content in retrieved text."""
    matches = [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text or "")]
    if matches:
        logger.warning("guardrail.injection.detected", source=source, patterns=matches[:3])
    return InjectionReport(clean=not matches, matches=matches, source=source)


def sanitise_retrieved_text(text: str, source: str = "corpus") -> str:
    """Neutralise instruction-shaped content and wrap the result as data.

    Matched spans are replaced rather than removed, so the agent can still see
    that something was filtered and mention it if relevant - silently deleting
    content would hide a tampering attempt from the audit trail.
    """
    if not text:
        return f"{_ENVELOPE_OPEN.format(source=source)}{_ENVELOPE_CLOSE}"

    report = scan_for_injection(text, source)
    cleaned = text
    if not report.clean:
        for pattern in INJECTION_PATTERNS:
            cleaned = pattern.sub("[filtered: instruction-like content]", cleaned)

    return f"{_ENVELOPE_OPEN.format(source=source)}\n{cleaned}\n{_ENVELOPE_CLOSE}"


__all__ = [
    "INJECTION_PATTERNS",
    "InjectionReport",
    "sanitise_retrieved_text",
    "scan_for_injection",
]
