"""Numeric grounding: the anti-hallucination gate.

The single most damaging failure mode for an analyst agent is a plausible
number that is not real. A wrong adjective is survivable; "₹1,240 crore growing
at 31 per cent" when the true figures are 759 and 28 is not, and it is exactly
the kind of error a fluent model makes when it is asked to summarise a table
from memory.

The defence is structural rather than probabilistic. Because every figure the
agent can legitimately state came from a tool result, the union of the tool
results is the complete allowed set. This module extracts every number from the
drafted answer and checks each one against that set within a tolerance. Anything
unmatched is reported, the draft is rejected, and the agent is asked to rewrite
using only the evidence it was given.

Two deliberate relaxations keep the check usable rather than merely strict:

* Numbers below a configured floor are ignored. Years, list positions and
  counts of two or three would otherwise generate constant false positives.
* A percentage is matched against both the raw ratio and the ratio times one
  hundred, because "0.284" in the evidence and "28.4%" in the prose are the
  same fact.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import get_framework
from ..logging_config import get_logger

logger = get_logger(__name__)

#: Matches integers, decimals and thousands-separated figures in prose.
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])[-+]?\d*\.?\d+")

#: Numbers inside these constructs are structural, not factual claims.
_STRIP_PATTERNS = (
    re.compile(r"\[S-\d+\]"),  # citation markers
    re.compile(r"\bhttps?://\S+"),  # URLs
    re.compile(r"\b[A-Z]\d{2}[A-Z]\d{2}[A-Z]?\b"),  # ATC codes such as C02F0O
    re.compile(r"\bMAT\s+\w+'?\d{2}\b", re.IGNORECASE),
    re.compile(r"\bFEB'\d{2}\b", re.IGNORECASE),
    re.compile(r"\b(19|20)\d{2}\b"),  # calendar years
    # Named identifiers that end in a number: S-01, NFHS-5, COVID-19, Opus-5.
    # Without this the "5" in "NFHS-5" reads as an unsupported numeric claim.
    re.compile(r"\b[A-Za-z][A-Za-z]+-\d+(?:\.\d+)?\b"),
)


@dataclass
class GroundingReport:
    """Result of checking one draft answer against its evidence."""

    passed: bool
    checked: int
    ungrounded: list[float] = field(default_factory=list)
    tolerance: float = 0.02
    ignored_below: float = 3.0

    def message(self) -> str:
        if self.passed:
            return f"All {self.checked} numeric claims matched the evidence pack."
        formatted = ", ".join(f"{value:g}" for value in self.ungrounded[:8])
        return (
            f"{len(self.ungrounded)} of {self.checked} numbers in the draft do not appear "
            f"in any tool result: {formatted}. Rewrite using only figures returned by the "
            "tools, or call another tool to obtain them."
        )


def _to_float(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def collect_numbers(payload: Any, into: set[float] | None = None) -> set[float]:
    """Every number reachable in a tool result, including inside strings.

    Strings are scanned as well as numeric fields because several tools embed
    figures in explanatory sentences (the trade-off narratives, for example),
    and those are legitimate sources for the answer to quote.
    """
    accumulator: set[float] = into if into is not None else set()

    if isinstance(payload, bool):
        return accumulator
    if isinstance(payload, (int, float)):
        accumulator.add(float(payload))
        # Percentage / ratio duality: evidence may hold either form.
        accumulator.add(round(float(payload) * 100.0, 6))
        accumulator.add(round(float(payload) / 100.0, 6))
        return accumulator
    if isinstance(payload, str):
        for match in _NUMBER.finditer(payload):
            value = _to_float(match.group())
            if value is not None:
                accumulator.add(value)
        return accumulator
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str):
                collect_numbers(key, accumulator)
            collect_numbers(value, accumulator)
        return accumulator
    if isinstance(payload, (list, tuple, set)):
        for item in payload:
            collect_numbers(item, accumulator)
        return accumulator
    return accumulator


def _extract_claims(text: str, ignore_below: float) -> list[float]:
    """Numbers a reader would treat as factual claims."""
    cleaned = text
    for pattern in _STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    claims: list[float] = []
    for match in _NUMBER.finditer(cleaned):
        value = _to_float(match.group())
        if value is None:
            continue
        if abs(value) < ignore_below:
            continue
        claims.append(value)
    return claims


def check_numeric_grounding(
    answer: str,
    evidence: Any,
    *,
    tolerance: float | None = None,
    ignore_below: float | None = None,
) -> GroundingReport:
    """Verify every number in ``answer`` appears in ``evidence``.

    Args:
        answer: The drafted response.
        evidence: Any structure of tool results.
        tolerance: Relative tolerance for a match. Defaults to config.
        ignore_below: Absolute floor under which numbers are ignored.

    Returns:
        A :class:`GroundingReport`. ``passed`` is False when any number in the
        answer cannot be traced to the evidence.
    """
    framework = get_framework()
    tol = float(
        tolerance
        if tolerance is not None
        else framework.get_path("guardrails.numeric_tolerance", 0.02)
    )
    floor = float(
        ignore_below
        if ignore_below is not None
        else framework.get_path("guardrails.numeric_ignore_below", 3.0)
    )

    allowed = collect_numbers(evidence)
    claims = _extract_claims(answer, floor)

    ungrounded: list[float] = []
    for claim in claims:
        target = abs(claim)
        window = max(tol * target, 0.005)
        if not any(abs(abs(candidate) - target) <= window for candidate in allowed):
            ungrounded.append(claim)

    report = GroundingReport(
        passed=not ungrounded,
        checked=len(claims),
        ungrounded=ungrounded,
        tolerance=tol,
        ignored_below=floor,
    )
    logger.info(
        "guardrail.numeric_grounding",
        passed=report.passed,
        checked=report.checked,
        ungrounded=len(ungrounded),
        allowed_values=len(allowed),
    )
    return report


def evidence_digest(evidence: Any, limit: int = 4000) -> str:
    """Compact JSON view of the evidence, for logging and debugging."""
    try:
        text = json.dumps(evidence, default=str, sort_keys=True)
    except (TypeError, ValueError):
        text = str(evidence)
    return text[:limit]


__all__ = [
    "GroundingReport",
    "check_numeric_grounding",
    "collect_numbers",
    "evidence_digest",
]
