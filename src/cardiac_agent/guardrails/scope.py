"""Scope control.

The agent knows one market: India Cardiac, as supplied. Asked about respiratory
volumes, next quarter's share price or how to price a launch in Brazil, the
correct behaviour is to say it cannot answer and explain what it does cover -
not to produce a confident guess from parametric memory.

The check runs before any tool executes, so an out-of-scope question costs
nothing and cannot contaminate the transcript with retrieved material that was
never relevant.

Deliberately permissive in one direction: anything ambiguous is allowed
through, because the downstream numeric guardrail catches an answer that has no
evidence behind it. Refusing a legitimate question is a worse failure here than
letting a marginal one reach the tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)

#: Vocabulary that places a question inside the case.
IN_SCOPE_TERMS: tuple[str, ...] = (
    "cardiac", "cardio", "hypertens", "lipid", "statin", "angina", "blood pressure",
    "cipla", "molecule", "segment", "sub-segment", "sub segment", "opportunity",
    "market", "share", "growth", "competitor", "brand", "portfolio", "prioriti",
    "right to win", "whitespace", "white space", "forecast", "mat", "sales",
    "telmisartan", "amlodipine", "rosuvastatin", "atorvastatin", "cilnidipine",
    "ezetimibe", "fenofibrate", "clopidogrel", "metoprolol", "bisoprolol",
    "nitrate", "nicorandil", "arb", "ccb", "ace", "diuretic", "combination",
    "fdc", "score", "rank", "signal", "trend", "hhi", "concentration",
    # Strategy vocabulary. A question can be squarely in scope without naming a
    # molecule: "where should we invest" is exactly what the case asks.
    "invest", "focus", "recommend", "strategy", "strategic", "launch", "enter",
    "expand", "defend", "double down", "capability", "penetrat", "molecule",
    "therapy", "sub-segment", "space", "spaces", "audit", "dataset", "data",
    "volume", "value", "price", "erosion", "leader", "player", "franchise",
)

#: Topics the dataset simply does not contain. These refuse unconditionally,
#: because no amount of in-scope vocabulary makes them answerable: "what is
#: Cipla's share price" names the company and the word "share" and is still a
#: question about a market this system has no data for.
HARD_BLOCK_TERMS: tuple[str, ...] = (
    "share price", "stock price", "market cap", "valuation", "shareholder",
    "acquisition target", "salary", "recruit", "hiring",
    "medical advice", "dosage for me", "prescribe me", "diagnose me",
    "legal advice", "should i take", "is it safe for me",
)

#: Adjacent therapy areas. These refuse only when nothing in-scope is present,
#: because "how does cardiac compare with respiratory" is a legitimate framing
#: question that the market totals can partly answer.
SOFT_BLOCK_TERMS: tuple[str, ...] = (
    "respiratory", "oncology", "dermatology", "vaccine", "diabetes market",
    "anti-infective", "urology", "central nervous system",
)

#: Retained for backwards compatibility with callers that imported the old name.
OUT_OF_SCOPE_TERMS: tuple[str, ...] = HARD_BLOCK_TERMS + SOFT_BLOCK_TERMS

#: Attempts to make the agent abandon its instructions.
_OVERRIDE_PATTERNS = (
    re.compile(r"ignore (?:all |your |the )?(?:previous|prior|above|earlier) instructions", re.I),
    re.compile(r"disregard (?:your|the) (?:system prompt|instructions|guardrails)", re.I),
    re.compile(r"you are now\b", re.I),
    re.compile(r"reveal (?:your |the )?(?:system prompt|instructions)", re.I),
    re.compile(r"\bdeveloper mode\b", re.I),
)


@dataclass
class ScopeDecision:
    """Whether a question should be answered, and why not if not."""

    allowed: bool
    reason: str = ""
    refusal_text: str = ""


REFUSAL_TEMPLATE = (
    "That falls outside what this agent can answer. It works from one dataset: the "
    "India Cardiac prescription audit supplied with the case, covering "
    "anti-hypertensives, lipid regulators and anti-anginals to MAT February 2026, "
    "plus a curated corpus of external cardiovascular signals.\n\n"
    "It can tell you about market size and growth, real versus price-led growth, "
    "competitive concentration, Cipla's position and right to win, underpenetrated "
    "spaces, three-to-five-year projections and how sensitive any ranking is to the "
    "framework's weights.\n\n"
    "{detail}"
)


def check_scope(question: str) -> ScopeDecision:
    """Decide whether a question is answerable from the supplied data."""
    if not get_settings().enforce_scope:
        return ScopeDecision(allowed=True, reason="scope enforcement disabled")

    text = question.strip()
    if not text:
        return ScopeDecision(
            allowed=False,
            reason="empty question",
            refusal_text="Ask a question about the Cardiac market and I will work through it.",
        )

    for pattern in _OVERRIDE_PATTERNS:
        if pattern.search(text):
            logger.warning("guardrail.scope.override_attempt", question=text[:200])
            return ScopeDecision(
                allowed=False,
                reason="instruction override attempt",
                refusal_text=(
                    "I only answer questions about the Cardiac market analysis, and I keep "
                    "my operating instructions private. Ask me about the market, the "
                    "opportunity spaces or Cipla's position and I will help."
                ),
            )

    lowered = text.lower()
    hard_blocks = [term for term in HARD_BLOCK_TERMS if term in lowered]
    soft_blocks = [term for term in SOFT_BLOCK_TERMS if term in lowered]
    in_scope = [term for term in IN_SCOPE_TERMS if term in lowered]

    if hard_blocks:
        logger.info("guardrail.scope.hard_block", terms=hard_blocks[:3])
        return ScopeDecision(
            allowed=False,
            reason=f"topic absent from the dataset: {', '.join(hard_blocks[:3])}",
            refusal_text=REFUSAL_TEMPLATE.format(
                detail=(
                    f"Your question is about {hard_blocks[0]}, which this dataset does not "
                    "contain. It is a prescription-audit extract: value, volume, price and "
                    "competitive structure, with no financial-market, employment or "
                    "clinical-advice content."
                )
            ),
        )

    # An adjacent therapy area only blocks when nothing in-scope is present. A
    # question like "how does the cardiac portfolio compare with respiratory"
    # is a legitimate framing question and should reach the tools.
    if soft_blocks and not in_scope:
        logger.info("guardrail.scope.soft_block", terms=soft_blocks[:3])
        return ScopeDecision(
            allowed=False,
            reason=f"out-of-scope therapy area: {', '.join(soft_blocks[:3])}",
            refusal_text=REFUSAL_TEMPLATE.format(
                detail=(
                    f"Your question is about {soft_blocks[0]}, and this dataset covers the "
                    "Cardiac therapy area only."
                )
            ),
        )

    # Nothing in the question connects it to this market. Answering anyway
    # would mean producing market context that has no bearing on what was
    # asked, which reads as a non-sequitur rather than as a refusal.
    if not in_scope:
        logger.info("guardrail.scope.no_anchor", question=text[:160])
        return ScopeDecision(
            allowed=False,
            reason="no in-scope terminology",
            refusal_text=REFUSAL_TEMPLATE.format(
                detail=(
                    "Nothing in your question connects it to that dataset, so I have no "
                    "evidence to answer from. Rephrase it around a segment, molecule, "
                    "competitor or Cipla's position and I will work through it."
                )
            ),
        )

    return ScopeDecision(allowed=True, reason="in scope")


__all__ = [
    "HARD_BLOCK_TERMS",
    "IN_SCOPE_TERMS",
    "OUT_OF_SCOPE_TERMS",
    "REFUSAL_TEMPLATE",
    "SOFT_BLOCK_TERMS",
    "ScopeDecision",
    "check_scope",
]
