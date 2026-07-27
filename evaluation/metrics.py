"""Evaluation metrics.

What is measured and why:

``groundedness``      Share of answers in which every stated number traced back
                      to a tool result. The headline metric. A system that
                      scores below one here is not usable for this task.
``tool_recall``       Did the agent reach the evidence the question needed.
                      Catches an agent that answers fluently from the wrong
                      data, which is invisible in a groundedness score.
``citation_validity`` Every ``[S-xx]`` marker resolves to a real signal.
``content_coverage``  Does the answer name the substance the question was about.
``refusal_accuracy``  Out-of-scope questions refused, in-scope ones answered.
``latency``           Wall clock, because a demonstration has a time budget.

Deliberately not measured by another language model. An LLM-as-judge score
would be cheap to produce and impossible to defend in front of a panel that
asks how the judge was validated. Every metric here is a deterministic
assertion against the run.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    """Outcome for one golden question."""

    case_id: str
    question: str
    passed: bool
    grounded: bool | None
    tools_called: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    missing_content: list[str] = field(default_factory=list)
    forbidden_content: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    refused: bool = False
    expected_refusal: bool = False
    answer_length: int = 0
    latency_ms: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "grounded": self.grounded,
            "tools_called": self.tools_called,
            "missing_tools": self.missing_tools,
            "missing_content": self.missing_content,
            "invalid_citations": self.invalid_citations,
            "refused": self.refused,
            "expected_refusal": self.expected_refusal,
            "answer_length": self.answer_length,
            "latency_ms": round(self.latency_ms, 1),
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class EvaluationSummary:
    """Aggregate scores across the golden set."""

    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def groundedness(self) -> float:
        checked = [r for r in self.results if r.grounded is not None and not r.expected_refusal]
        if not checked:
            return 1.0
        return sum(1 for r in checked if r.grounded) / len(checked)

    @property
    def tool_recall(self) -> float:
        relevant = [r for r in self.results if not r.expected_refusal]
        if not relevant:
            return 1.0
        return sum(1 for r in relevant if not r.missing_tools) / len(relevant)

    @property
    def citation_validity(self) -> float:
        relevant = [r for r in self.results if not r.expected_refusal]
        if not relevant:
            return 1.0
        return sum(1 for r in relevant if not r.invalid_citations) / len(relevant)

    @property
    def content_coverage(self) -> float:
        relevant = [r for r in self.results if not r.expected_refusal]
        if not relevant:
            return 1.0
        return sum(1 for r in relevant if not r.missing_content) / len(relevant)

    @property
    def refusal_accuracy(self) -> float:
        if not self.results:
            return 1.0
        correct = sum(1 for r in self.results if r.refused == r.expected_refusal)
        return correct / len(self.results)

    @property
    def median_latency_ms(self) -> float:
        latencies = [r.latency_ms for r in self.results if r.latency_ms > 0]
        return statistics.median(latencies) if latencies else 0.0

    @property
    def p95_latency_ms(self) -> float:
        latencies = sorted(r.latency_ms for r in self.results if r.latency_ms > 0)
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))
        return latencies[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "groundedness": round(self.groundedness, 4),
            "tool_recall": round(self.tool_recall, 4),
            "citation_validity": round(self.citation_validity, 4),
            "content_coverage": round(self.content_coverage, 4),
            "refusal_accuracy": round(self.refusal_accuracy, 4),
            "median_latency_ms": round(self.median_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "results": [result.to_dict() for result in self.results],
        }

    def failures(self) -> list[CaseResult]:
        return [result for result in self.results if not result.passed]


__all__ = ["CaseResult", "EvaluationSummary"]
