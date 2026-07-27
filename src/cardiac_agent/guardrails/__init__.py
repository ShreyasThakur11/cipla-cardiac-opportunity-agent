"""Checks that sit between the model and the user.

The agent is allowed to be wrong about wording. It is not allowed to be wrong
about a number, to attribute an external claim to nothing, or to answer a
question it has no data for. Each of those is a separate check with its own
module, and they are composed by :mod:`~cardiac_agent.guardrails.pipeline`.

The order matters. Scope is checked before any work is done, so an off-topic
question costs nothing. Grounding and citations are checked after the answer is
drafted, because that is the only point at which there is something to check.
"""

from .citations import CitationReport, check_citations
from .injection import sanitise_retrieved_text, scan_for_injection
from .numeric_grounding import GroundingReport, check_numeric_grounding, collect_numbers
from .pipeline import GuardrailOutcome, run_output_guardrails
from .scope import ScopeDecision, check_scope

__all__ = [
    "CitationReport",
    "GroundingReport",
    "GuardrailOutcome",
    "ScopeDecision",
    "check_citations",
    "check_numeric_grounding",
    "check_scope",
    "collect_numbers",
    "run_output_guardrails",
    "sanitise_retrieved_text",
    "scan_for_injection",
]
