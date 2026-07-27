"""Run the golden question set against the agent.

    python evaluation/run_eval.py
    python evaluation/run_eval.py --case Q02 --verbose
    python evaluation/run_eval.py --json results.json

Runs against whatever provider is configured. Set ``CARDIAC_LLM_PROVIDER=none``
to evaluate the deterministic path, which is the one to gate a release on:
it is reproducible, so a regression in it is a real regression rather than
model variance.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.metrics import CaseResult, EvaluationSummary  # noqa: E402

GOLDEN_PATH = PROJECT_ROOT / "evaluation" / "golden_questions.yaml"


def load_cases(path: Path = GOLDEN_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = yaml.safe_load(handle) or []
    if not isinstance(cases, list):
        raise ValueError(f"{path} must contain a list of cases.")
    return cases


def evaluate_case(agent: Any, case: dict[str, Any]) -> CaseResult:
    """Run one case and score it."""
    question = case["question"]
    expected_refusal = bool(case.get("expect_refusal", False))

    started = time.perf_counter()
    outcome = agent.ask(question)
    latency_ms = (time.perf_counter() - started) * 1000.0

    answer = outcome.answer or ""
    lowered = answer.lower()
    state = outcome.state
    tools_called = state.tools_used
    reasons: list[str] = []

    if expected_refusal:
        if not state.refused:
            reasons.append("expected a refusal but the agent answered")
        return CaseResult(
            case_id=case["id"],
            question=question,
            passed=state.refused,
            grounded=None,
            tools_called=tools_called,
            refused=state.refused,
            expected_refusal=True,
            answer_length=len(answer),
            latency_ms=latency_ms,
            failure_reasons=reasons,
        )

    if state.refused:
        reasons.append("agent refused an in-scope question")

    missing_tools = [
        tool for tool in case.get("required_tools", []) or [] if tool not in tools_called
    ]
    if missing_tools:
        reasons.append(f"did not call required tool(s): {', '.join(missing_tools)}")

    missing_content = [
        needle for needle in case.get("must_include", []) or [] if needle.lower() not in lowered
    ]
    if missing_content:
        reasons.append(f"answer omits: {', '.join(missing_content)}")

    forbidden = [
        needle for needle in case.get("must_not_include", []) or [] if needle.lower() in lowered
    ]
    if forbidden:
        reasons.append(f"answer contains forbidden content: {', '.join(forbidden)}")

    min_length = int(case.get("min_length", 0) or 0)
    if len(answer) < min_length:
        reasons.append(f"answer is {len(answer)} characters, below the {min_length} minimum")

    guard = state.guardrails
    grounded = guard.grounding.passed if guard and guard.grounding else None
    if grounded is False:
        reasons.append("numeric grounding failed")

    invalid_citations = list(guard.citations.unknown) if guard and guard.citations else []
    if invalid_citations:
        reasons.append(f"unresolvable citations: {', '.join(invalid_citations)}")

    return CaseResult(
        case_id=case["id"],
        question=question,
        passed=not reasons,
        grounded=grounded,
        tools_called=tools_called,
        missing_tools=missing_tools,
        missing_content=missing_content,
        forbidden_content=forbidden,
        invalid_citations=invalid_citations,
        refused=state.refused,
        expected_refusal=False,
        answer_length=len(answer),
        latency_ms=latency_ms,
        failure_reasons=reasons,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Cardiac Opportunity Agent.")
    parser.add_argument("--case", action="append", help="Run only these case ids.")
    parser.add_argument("--json", type=Path, help="Write the full results to this file.")
    parser.add_argument("--verbose", action="store_true", help="Print each answer.")
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.85,
        help="Exit non-zero below this pass rate (default 0.85).",
    )
    arguments = parser.parse_args()

    from cardiac_agent.agent import build_agent
    from cardiac_agent.config import get_settings
    from cardiac_agent.logging_config import configure_logging

    configure_logging("WARNING")
    settings = get_settings()

    cases = load_cases()
    if arguments.case:
        wanted = {value.upper() for value in arguments.case}
        cases = [case for case in cases if str(case["id"]).upper() in wanted]
        if not cases:
            print(f"No cases matched {sorted(wanted)}.")
            return 2

    print(f"Evaluating {len(cases)} case(s) with provider={settings.llm_provider}")
    print("-" * 88)

    agent = build_agent()
    results = []
    for case in cases:
        result = evaluate_case(agent, case)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(
            f"[{status}] {result.case_id}  {case['question'][:62]:<64} {result.latency_ms:7.0f} ms"
        )
        if not result.passed:
            for reason in result.failure_reasons:
                print(f"         - {reason}")
        if arguments.verbose:
            print(f"         tools: {', '.join(result.tools_called) or 'none'}")

    summary = EvaluationSummary(results=results)
    print("-" * 88)
    print(f"pass rate          {summary.pass_rate:.1%}  ({summary.passed}/{summary.total})")
    print(f"groundedness       {summary.groundedness:.1%}")
    print(f"tool recall        {summary.tool_recall:.1%}")
    print(f"citation validity  {summary.citation_validity:.1%}")
    print(f"content coverage   {summary.content_coverage:.1%}")
    print(f"refusal accuracy   {summary.refusal_accuracy:.1%}")
    print(f"median latency     {summary.median_latency_ms:.0f} ms")
    print(f"p95 latency        {summary.p95_latency_ms:.0f} ms")

    if arguments.json:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        print(f"\nWrote {arguments.json}")

    if summary.pass_rate < arguments.min_pass_rate:
        print(f"\nFAILED: pass rate below the {arguments.min_pass_rate:.0%} threshold.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
