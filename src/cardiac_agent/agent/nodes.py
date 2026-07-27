"""The agent's nodes.

Each function is one step in the graph. A node takes the shared state, does one
thing, mutates the state, and returns the name of the next node. Nothing else -
no node calls another node directly, so the control flow is entirely visible in
:mod:`~cardiac_agent.agent.graph`.

The plan node is worth reading closely. It does two jobs: it classifies the
question into an intent, which drives a deterministic baseline set of tool
calls, and it lets the model add to that set. The baseline matters because it
means the agent gathers the right evidence even when the model chooses badly,
and it is what makes the no-credentials path work at all.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..config import get_framework, get_settings
from ..guardrails.injection import sanitise_retrieved_text
from ..guardrails.pipeline import run_output_guardrails
from ..guardrails.scope import check_scope
from ..logging_config import get_logger
from ..pipeline import AnalysisContext
from .llm import LLMClient, LLMResponse
from .prompts import load_prompt
from .state import AgentState, ToolInvocation
from .templates import render_answer
from .tools import ToolError, ToolSpec

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Intent classification
# --------------------------------------------------------------------------

#: Question shapes the case asks for, mapped to the evidence each one needs.
#: Order matters: the first pattern that matches wins, so the narrower
#: intents are listed before the broader ones. "How robust is the ranking"
#: must reach `sensitivity` rather than being caught by the `rank` in
#: `top_opportunities`.
INTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "sensitivity",
        re.compile(r"sensitiv|robust|how confident|what if.*weight|stability|hold up", re.I),
    ),
    (
        "underpenetration",
        re.compile(
            r"underpenetrat|under-penetrat|white ?space|absent|not present|below fair share", re.I
        ),
    ),
    (
        "prioritisation",
        re.compile(
            r"prioriti[sz]|which (?:two|three|2|3|ones?)|should cipla (?:focus|invest|back)|double down",
            re.I,
        ),
    ),
    (
        "right_to_win",
        re.compile(
            r"right to win|compare(?:d)? with (?:key )?competitors?|competitive (?:strength|position)",
            re.I,
        ),
    ),
    (
        "strategic_implications",
        re.compile(
            r"strategic implication|where should (?:the company|cipla)|build capabilit|avoid|harvest|selective",
            re.I,
        ),
    ),
    (
        "forecast",
        re.compile(r"forecast|project|next (?:3|5|three|five)|outperform|over the next", re.I),
    ),
    (
        "top_opportunities",
        re.compile(r"top \d|best opportunit|which opportunit|identify.*opportunit|\brank\b", re.I),
    ),
    (
        "competitor",
        re.compile(
            r"\b(torrent|sun|usv|glenmark|mankind|lupin|zydus|macleods|intas|aristo|micro labs|emcure|alembic|dr\.? ?reddy|ipca|ajanta|eris|abbott|pfizer)\b",
            re.I,
        ),
    ),
    ("space_detail", re.compile(r"tell me about|deep dive|explain|what is happening in", re.I)),
    ("overview", re.compile(r"overview|how big|market size|summar|landscape", re.I)),
)

#: Same patterns, addressable by name.
INTENT_PATTERN_BY_NAME: dict[str, re.Pattern[str]] = dict(INTENT_PATTERNS)

#: Baseline evidence gathered for each intent, before the model adds anything.
INTENT_PLANS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "overview": [("market_overview", {})],
    "top_opportunities": [
        ("market_overview", {}),
        (
            "rank_opportunity_spaces",
            {"level": "molecule_combination", "rank_by": "market_opportunity_index", "top_n": 8},
        ),
        (
            "rank_opportunity_spaces",
            {"level": "sub_segment", "rank_by": "market_opportunity_index", "top_n": 6},
        ),
    ],
    "prioritisation": [
        ("market_overview", {}),
        (
            "rank_opportunity_spaces",
            {"level": "molecule_combination", "rank_by": "cipla_priority_score", "top_n": 8},
        ),
        ("cipla_portfolio", {}),
        ("sensitivity_analysis", {"level": "molecule_combination", "top_k": 5}),
    ],
    "right_to_win": [
        ("market_overview", {}),
        ("cipla_portfolio", {}),
        (
            "rank_opportunity_spaces",
            {"level": "sub_segment", "rank_by": "cipla_priority_score", "top_n": 6},
        ),
    ],
    "underpenetration": [
        ("market_overview", {}),
        ("whitespace_scan", {"limit": 8}),
        ("cipla_portfolio", {}),
    ],
    "strategic_implications": [
        ("market_overview", {}),
        (
            "rank_opportunity_spaces",
            {"level": "sub_segment", "rank_by": "cipla_priority_score", "top_n": 12},
        ),
        ("cipla_portfolio", {}),
    ],
    "forecast": [
        ("market_overview", {}),
        (
            "rank_opportunity_spaces",
            {"level": "molecule_combination", "rank_by": "market_opportunity_index", "top_n": 6},
        ),
    ],
    "sensitivity": [
        ("sensitivity_analysis", {"level": "molecule_combination", "top_k": 5}),
    ],
    "competitor": [("market_overview", {})],
    "space_detail": [("market_overview", {})],
    "general": [("market_overview", {})],
}


def classify_intent(question: str) -> str:
    """Map a question to the evidence shape it needs."""
    for intent, pattern in INTENT_PATTERNS:
        if pattern.search(question):
            return intent
    return "general"


def _mentioned_spaces(question: str, context: AnalysisContext, limit: int = 3) -> list[str]:
    """Space labels the question names explicitly.

    Matching on molecule tokens rather than the full label is what lets
    "how does cilnidipine plus telmisartan look" resolve without the user
    knowing the audit's naming convention.
    """
    tokens = {token.upper() for token in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", question)}
    if not tokens:
        return []
    scored = context.scored
    hits: list[tuple[float, str]] = []
    for _, row in scored.iterrows():
        label = str(row["space_label"]).upper()
        overlap = sum(1 for token in tokens if token in label)
        if overlap:
            hits.append((overlap * 1000.0 + float(row["value_t2"]), str(row["space_id"])))
    hits.sort(reverse=True)
    return [space_id for _, space_id in hits[:limit]]


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


def scope_node(state: AgentState, context: AnalysisContext, **_: Any) -> str:
    """Reject out-of-scope questions before any work is done."""
    state.node_path.append("scope")
    decision = check_scope(state.question)
    if not decision.allowed:
        state.refused = True
        state.refusal_reason = decision.reason
        state.answer = decision.refusal_text
        return "END"
    return "plan"


def plan_node(state: AgentState, context: AnalysisContext, **_: Any) -> str:
    """Classify the question and lay out the baseline evidence to gather."""
    state.node_path.append("plan")
    state.intent = classify_intent(state.question)

    plan = list(INTENT_PLANS.get(state.intent, INTENT_PLANS["general"]))

    # Add a deep dive for any space the question names.
    for space_id in _mentioned_spaces(state.question, context):
        plan.append(("space_deep_dive", {"space": space_id}))

    # Anything about the outside world gets a retrieval pass.
    if state.intent in {
        "top_opportunities",
        "prioritisation",
        "underpenetration",
        "strategic_implications",
        "forecast",
    } or re.search(
        r"guideline|trend|external|policy|regulat|patent|epidemi|pollution|approval",
        state.question,
        re.I,
    ):
        plan.append(("retrieve_external_signals", {"query": state.question, "top_k": 5}))

    if state.intent == "competitor":
        match = INTENT_PATTERN_BY_NAME["competitor"].search(state.question)
        if match:
            plan.append(("competitor_profile", {"company": match.group(0)}))

    state.plan = [f"{name}({arguments})" for name, arguments in plan]
    state.baseline_plan = plan
    logger.info("agent.plan", intent=state.intent, steps=len(plan))
    return "gather"


def _execute_tool(spec: ToolSpec, arguments: dict[str, Any], state: AgentState) -> ToolInvocation:
    """Run one tool and record the outcome, never raising into the graph."""
    started = time.perf_counter()
    try:
        result = spec.handler(**arguments)
        invocation = ToolInvocation(
            name=spec.name,
            arguments=arguments,
            ok=True,
            result=result,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    except ToolError as exc:
        invocation = ToolInvocation(
            name=spec.name,
            arguments=arguments,
            ok=False,
            error=str(exc),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        logger.info("agent.tool.rejected", tool=spec.name, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a tool bug must not kill the run
        invocation = ToolInvocation(
            name=spec.name,
            arguments=arguments,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        logger.error("agent.tool.failed", tool=spec.name, error=str(exc), exc_info=True)
    state.record_tool(invocation)
    return invocation


def gather_node(
    state: AgentState,
    context: AnalysisContext,
    tools: dict[str, ToolSpec],
    llm: LLMClient,
    **_: Any,
) -> str:
    """Execute the baseline plan, then let the model call further tools."""
    state.node_path.append("gather")

    for name, arguments in state.baseline_plan:
        spec = tools.get(name)
        if spec is None:
            continue
        _execute_tool(spec, dict(arguments), state)

    if not llm.available:
        state.deterministic = True
        return "synthesize"

    framework = get_framework()
    max_iterations = int(framework.get_path("agent.max_tool_iterations", 8))
    system = load_prompt("system")

    baseline_summary = _summarise_evidence(state)
    state.messages = [
        {
            "role": "user",
            "content": (
                f"{state.question}\n\n"
                "The following evidence has already been gathered for you. Call further "
                "tools only if something you need is missing, then answer.\n\n"
                f"{baseline_summary}"
            ),
        }
    ]

    schemas = [spec.to_anthropic() for spec in tools.values()]

    for iteration in range(max_iterations):
        try:
            response: LLMResponse = llm.complete(
                system=system, messages=state.messages, tools=schemas
            )
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail
            logger.warning("agent.llm.failed", error=str(exc), iteration=iteration)
            state.warnings.append(
                f"Model call failed ({type(exc).__name__}); answered deterministically."
            )
            state.deterministic = True
            return "synthesize"

        state.add_usage(response.usage)

        if response.refused:
            state.warnings.append("The model declined to answer; answered deterministically.")
            state.deterministic = True
            return "synthesize"

        if not response.wants_tools:
            state.draft = response.text
            state.messages.append(
                {"role": "assistant", "content": response.raw_content or response.text}
            )
            return "verify" if state.draft.strip() else "synthesize"

        state.messages.append({"role": "assistant", "content": response.raw_content})

        results: list[dict[str, Any]] = []
        for call in response.tool_calls:
            spec = tools.get(call.name)
            if spec is None:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": f"Unknown tool '{call.name}'. Available: {sorted(tools)}.",
                        "is_error": True,
                    }
                )
                continue
            invocation = _execute_tool(spec, call.arguments, state)
            payload = (
                _stringify(invocation.result)
                if invocation.ok
                else f"Tool error: {invocation.error}"
            )
            if spec.name in {"retrieve_external_signals", "sql_query"}:
                payload = sanitise_retrieved_text(payload, source=spec.name)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": payload,
                    "is_error": not invocation.ok,
                }
            )
        # All results for one assistant turn go back in a single user message.
        state.messages.append({"role": "user", "content": results})

    state.warnings.append(
        f"Reached the {max_iterations}-call tool limit; answering from the evidence gathered."
    )
    return "synthesize"


def _stringify(payload: Any, limit: int = 12_000) -> str:
    import json

    try:
        text = json.dumps(payload, default=str, indent=2)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated at {limit} characters]"
    return text


def _summarise_evidence(state: AgentState) -> str:
    """Compact rendering of the baseline evidence for the first model turn."""
    blocks = [
        f"### {name}\n{_stringify(payload, limit=6000)}"
        for name, payload in state.evidence.items()
        if not name.startswith("_")
    ]
    return "\n\n".join(blocks) if blocks else "(no baseline evidence)"


def synthesize_node(state: AgentState, context: AnalysisContext, llm: LLMClient, **_: Any) -> str:
    """Write the answer, either with the model or from templates."""
    state.node_path.append("synthesize")

    if state.deterministic or not llm.available:
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    if state.draft.strip():
        return "verify"

    state.messages.append({"role": "user", "content": load_prompt("synthesizer")})
    try:
        response = llm.complete(system=load_prompt("system"), messages=state.messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent.synthesize.failed", error=str(exc))
        state.warnings.append("Synthesis call failed; answered deterministically.")
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    state.add_usage(response.usage)
    if response.refused or not response.text.strip():
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    state.draft = response.text
    state.messages.append({"role": "assistant", "content": response.raw_content or response.text})
    return "verify"


def verify_node(state: AgentState, context: AnalysisContext, llm: LLMClient, **_: Any) -> str:
    """Check the draft against the evidence; ask for one rewrite if it fails."""
    state.node_path.append("verify")

    known_ids = {signal.id for signal in context.corpus}
    evidence = {key: value for key, value in state.evidence.items() if not key.startswith("_")}
    outcome = run_output_guardrails(state.draft, evidence, known_ids)
    state.guardrails = outcome
    state.warnings.extend(outcome.warnings)

    if outcome.passed:
        state.answer = state.draft
        return "END"

    max_retries = int(get_framework().get_path("guardrails.max_verification_retries", 1))
    if state.verification_attempts >= max_retries or not llm.available:
        # Budget spent. Return the evidence-backed rendering rather than an
        # answer we know contains an unsupported figure.
        state.warnings.append(
            "The drafted narrative could not be fully grounded, so a deterministic "
            "rendering of the evidence was returned instead."
        )
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    state.verification_attempts += 1
    state.messages.append(
        {"role": "user", "content": load_prompt("verifier").format(feedback=outcome.feedback)}
    )
    try:
        response = llm.complete(system=load_prompt("system"), messages=state.messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent.verify.rewrite_failed", error=str(exc))
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    state.add_usage(response.usage)
    if response.refused or not response.text.strip():
        state.answer = render_answer(state.question, state.evidence, context)
        state.deterministic = True
        return "END"

    state.draft = response.text
    state.messages.append({"role": "assistant", "content": response.raw_content or response.text})
    return "verify"


def finalise_node(state: AgentState, context: AnalysisContext, **_: Any) -> str:
    """Attach citations and settings notes to the completed answer."""
    state.node_path.append("finalise")
    settings = get_settings()
    if not settings.enforce_numeric_grounding:
        state.warnings.append(
            "Numeric grounding was disabled for this run; figures were not verified."
        )
    return "END"


__all__ = [
    "INTENT_PATTERNS",
    "INTENT_PLANS",
    "classify_intent",
    "finalise_node",
    "gather_node",
    "plan_node",
    "scope_node",
    "synthesize_node",
    "verify_node",
]
