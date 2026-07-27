"""Agent state.

One mutable object threaded through the graph. Every node reads it, writes to
it and returns the name of the next node. Keeping state in a single typed
container rather than in closures is what makes a run reproducible from the
trace alone: dump the state at any point and you know exactly what the agent
knew when it made its next decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..guardrails.pipeline import GuardrailOutcome


@dataclass
class ToolInvocation:
    """One tool call and what it returned."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class AgentState:
    """Everything the agent knows while answering one question."""

    question: str
    trace_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Conversation with the model, in provider message format.
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Planning
    plan: list[str] = field(default_factory=list)
    intent: str = "general"
    #: Tool calls the planner scheduled before the model was consulted. These
    #: run regardless of what the model decides, which is what guarantees the
    #: agent gathers the right evidence even with no model available.
    baseline_plan: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    # Evidence
    invocations: list[ToolInvocation] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    # Output
    draft: str = ""
    answer: str = ""
    guardrails: GuardrailOutcome | None = None
    verification_attempts: int = 0
    refused: bool = False
    refusal_reason: str = ""
    deterministic: bool = False

    # Bookkeeping
    node_path: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def record_tool(self, invocation: ToolInvocation) -> None:
        """Store a tool result and make it available as evidence.

        Repeat calls to the same tool are keyed by an incrementing suffix so
        that a second, differently-parameterised call does not silently
        overwrite the first one's numbers in the evidence pack.
        """
        self.invocations.append(invocation)
        if not invocation.ok:
            return
        key = invocation.name
        if key in self.evidence:
            suffix = 2
            while f"{key}__{suffix}" in self.evidence:
                suffix += 1
            key = f"{key}__{suffix}"
        self.evidence[key] = invocation.result

    def add_usage(self, usage: dict[str, int]) -> None:
        for field_name, value in usage.items():
            self.usage[field_name] = self.usage.get(field_name, 0) + int(value)

    @property
    def elapsed_ms(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000.0

    @property
    def tools_used(self) -> list[str]:
        return [invocation.name for invocation in self.invocations if invocation.ok]

    def to_trace(self) -> dict[str, Any]:
        """Audit record for one run."""
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "intent": self.intent,
            "plan": self.plan,
            "node_path": self.node_path,
            "tools": [invocation.to_dict() for invocation in self.invocations],
            "verification_attempts": self.verification_attempts,
            "guardrails": self.guardrails.to_dict() if self.guardrails else None,
            "deterministic": self.deterministic,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "usage": self.usage,
            "warnings": self.warnings,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


__all__ = ["AgentState", "ToolInvocation"]
