"""The agent graph.

A small, explicit state machine: named nodes, a shared state object, and edges
returned by the nodes themselves.

``scope -> plan -> gather -> synthesize -> verify -> finalise``

with two conditional edges: ``scope`` can jump straight to the end on an
out-of-scope question, and ``verify`` loops back to itself once when the draft
fails grounding.

**On not using LangGraph.** The graph abstraction is right for this problem;
the dependency is not. LangGraph would bring LangChain's transitive tree into a
project whose entire model surface is one ``messages.create`` call, add a
version-compatibility risk to a system that has to run reliably in front of a
panel, and hide the control flow behind a builder API. What it would give back -
checkpointing, streaming, human-in-the-loop interrupts - this agent does not
use. Roughly a hundred lines of explicit dispatch buys the same semantics, runs
offline, and can be read end to end in one sitting. If the project later needs
durable execution across processes, the node signatures are already the shape
LangGraph expects and the swap is mechanical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..logging_config import get_logger, new_trace_id
from ..pipeline import AnalysisContext, get_context
from .llm import LLMClient, build_llm_client
from .nodes import (
    finalise_node,
    gather_node,
    plan_node,
    scope_node,
    synthesize_node,
    verify_node,
)
from .state import AgentState
from .tools import ToolSpec, build_tool_specs

logger = get_logger(__name__)

#: Hard stop on node transitions, so a mis-specified edge cannot spin forever.
MAX_TRANSITIONS = 24

NodeFn = Callable[..., str]

NODES: dict[str, NodeFn] = {
    "scope": scope_node,
    "plan": plan_node,
    "gather": gather_node,
    "synthesize": synthesize_node,
    "verify": verify_node,
    "finalise": finalise_node,
}

ENTRY_NODE = "scope"


@dataclass
class AgentAnswer:
    """The completed response plus everything needed to audit it."""

    answer: str
    state: AgentState
    citations: list[dict[str, str]]
    evidence: dict[str, Any]

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": self.answer,
            "trace": self.state.to_trace(),
            "citations": self.citations,
            "tools_used": self.state.tools_used,
            "deterministic": self.state.deterministic,
            "warnings": self.state.warnings,
        }
        if include_evidence:
            payload["evidence"] = self.evidence
        return payload


class CardiacAgent:
    """Answers questions about the Cardiac market opportunity."""

    def __init__(
        self,
        context: AnalysisContext | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.context = context or get_context()
        self.llm = llm if llm is not None else build_llm_client()
        self.tools: dict[str, ToolSpec] = build_tool_specs(self.context)
        logger.info(
            "agent.ready",
            tools=len(self.tools),
            model=getattr(self.llm, "model", "deterministic"),
            llm_available=self.llm.available,
            spaces_scored=len(self.context.scored),
        )

    def ask(self, question: str) -> AgentAnswer:
        """Run the graph to completion for one question."""
        trace_id = new_trace_id()
        state = AgentState(question=question.strip(), trace_id=trace_id)

        node = ENTRY_NODE
        transitions = 0
        while node != "END" and transitions < MAX_TRANSITIONS:
            handler = NODES.get(node)
            if handler is None:
                logger.error("agent.unknown_node", node=node)
                break
            next_node = handler(
                state,
                context=self.context,
                tools=self.tools,
                llm=self.llm,
            )
            transitions += 1
            node = next_node

        if transitions >= MAX_TRANSITIONS:
            state.warnings.append(
                "Graph hit its transition limit; returned the best answer available."
            )

        # finalise is reached by falling out of the loop rather than by an edge,
        # so that every path - including refusals - passes through it.
        if not state.refused:
            finalise_node(state, context=self.context)

        if not state.answer.strip():
            state.answer = (
                "No answer could be produced for that question. Try naming a specific "
                "sub-segment, molecule or competitor."
            )

        cited_ids = (
            set(state.guardrails.citations.cited)
            if state.guardrails and state.guardrails.citations
            else set()
        )
        citations = [
            citation
            for citation in self.context.citations()
            if not cited_ids or citation["id"] in cited_ids
        ]

        logger.info(
            "agent.answered",
            intent=state.intent,
            tools=state.tools_used,
            deterministic=state.deterministic,
            grounded=state.guardrails.passed if state.guardrails else None,
            elapsed_ms=round(state.elapsed_ms, 1),
        )
        return AgentAnswer(
            answer=state.answer,
            state=state,
            citations=citations,
            evidence={k: v for k, v in state.evidence.items() if not k.startswith("_")},
        )


def build_agent(
    context: AnalysisContext | None = None, llm: LLMClient | None = None
) -> CardiacAgent:
    """Convenience factory."""
    return CardiacAgent(context=context, llm=llm)


__all__ = ["ENTRY_NODE", "MAX_TRANSITIONS", "NODES", "AgentAnswer", "CardiacAgent", "build_agent"]
