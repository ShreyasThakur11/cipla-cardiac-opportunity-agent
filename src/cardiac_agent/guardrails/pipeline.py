"""Composing the output guardrails.

One entry point the agent calls once it has a draft. It returns a verdict, the
individual reports for the audit trail, and - when the draft fails - the exact
feedback to hand back to the model for a rewrite.

The rewrite budget is small on purpose. If an answer cannot be grounded in two
attempts, the honest outcome is to return the evidence and say the narrative
could not be verified, rather than to keep asking until something slips through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger
from .citations import CitationReport, check_citations
from .numeric_grounding import GroundingReport, check_numeric_grounding

logger = get_logger(__name__)


@dataclass
class GuardrailOutcome:
    """Verdict on one drafted answer."""

    passed: bool
    grounding: GroundingReport | None = None
    citations: CitationReport | None = None
    feedback: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "numeric_grounding": {
                "passed": self.grounding.passed if self.grounding else None,
                "numbers_checked": self.grounding.checked if self.grounding else 0,
                "ungrounded": self.grounding.ungrounded if self.grounding else [],
            },
            "citations": {
                "valid": self.citations.valid if self.citations else None,
                "cited": self.citations.cited if self.citations else [],
                "unknown": self.citations.unknown if self.citations else [],
                "uncited_claim_count": len(self.citations.uncited_claims)
                if self.citations
                else 0,
            },
            "warnings": self.warnings,
        }


def run_output_guardrails(
    answer: str, evidence: Any, known_signal_ids: set[str]
) -> GuardrailOutcome:
    """Check a drafted answer before it reaches the user.

    Args:
        answer: The model's draft.
        evidence: Every tool result gathered for this question.
        known_signal_ids: Signal identifiers present in the corpus.

    Returns:
        A :class:`GuardrailOutcome`. When ``passed`` is False, ``feedback``
        carries a specific, actionable correction for the model.
    """
    settings = get_settings()
    warnings: list[str] = []

    citations = check_citations(answer, known_signal_ids)
    if citations.uncited_claims:
        warnings.append(
            f"{len(citations.uncited_claims)} sentence(s) make an external claim without a citation."
        )

    grounding: GroundingReport | None = None
    if settings.enforce_numeric_grounding:
        grounding = check_numeric_grounding(answer, evidence)
    else:
        warnings.append("Numeric grounding is disabled by configuration.")

    failures: list[str] = []
    if grounding is not None and not grounding.passed:
        failures.append(grounding.message())
    if not citations.valid:
        failures.append(citations.message())

    outcome = GuardrailOutcome(
        passed=not failures,
        grounding=grounding,
        citations=citations,
        feedback=" ".join(failures),
        warnings=warnings,
    )
    logger.info(
        "guardrail.pipeline",
        passed=outcome.passed,
        failure_count=len(failures),
        warning_count=len(warnings),
    )
    return outcome


__all__ = ["GuardrailOutcome", "run_output_guardrails"]
