---
title: Evaluation
layout: default
nav_order: 14
---

# Evaluation

## What is measured, and why

Six metrics, all deterministic assertions against the run. Nothing is scored by
another language model.

That is a deliberate choice. An LLM-as-judge score is cheap to produce and
impossible to defend when a panel asks how the judge was validated. Every
number below can be recomputed by anyone with the repository.

| Metric | Definition | Why it exists |
| --- | --- | --- |
| **Groundedness** | Share of answers where every stated number traced to a tool result | The headline metric. Below 1.0 the system is not usable for this task. |
| **Tool recall** | Did the agent reach the evidence the question needed | Catches an agent that answers fluently from the wrong data, which groundedness alone cannot see. |
| **Citation validity** | Every `[S-xx]` marker resolves to a real signal | A fabricated source is worse than no source. |
| **Content coverage** | Does the answer name the substance the question was about | Catches a technically grounded answer that misses the point. |
| **Refusal accuracy** | Out-of-scope refused, in-scope answered | Both directions matter. Over-refusing is as bad as under-refusing. |
| **Latency** | Median and p95 wall clock | A live demonstration has a time budget. |

---

## The golden set

Fourteen cases in `evaluation/golden_questions.yaml`. Each states the question,
the tools the agent must reach for, and the substance the answer has to
contain. Checks are about behaviour rather than wording: an agent that gathers
the right evidence and names the right space passes even if it phrases things
differently, and one that produces fluent prose without calling the tools
fails.

| Case | Covers |
| --- | --- |
| Q01 | Top opportunities (case question 1a) |
| Q02 | Which two or three to prioritise (case question 1b) |
| Q03 | Underpenetration (case question 3) |
| Q04 | Right to win against competitors (case question 2) |
| Q05 | Strategic implications (case question 4) |
| Q06 | Reading MAT against MAT CP correctly |
| Q07 | Deep dive on a named space |
| Q08 | Rank stability |
| Q09 | Competitor profile |
| Q10 | **The trap.** Should Cipla enter saroglitazar given its growth? |
| Q11 | Out-of-scope refusal (share price) |
| Q12 | Instruction-override refusal |
| Q13 | Cross-hierarchy molecule franchises |
| Q14 | Five-year outperformance |

Q10 is the case that matters most. Saroglitazar has the highest growth in its
sub-segment and is originator-held. An agent that ranks on growth alone
recommends it. The competitive-headroom pillar exists to prevent that, and the
case verifies the behaviour rather than the reasoning.

Q08 exists because of a real defect found during development: "How robust is
the ranking?" was being routed to the ranking intent because the pattern for
top-opportunities matched the word "ranking" first. The intent patterns were
reordered so narrower intents win, and this case prevents a regression.

---

## Running it

```bash
CARDIAC_LLM_PROVIDER=none python evaluation/run_eval.py
python evaluation/run_eval.py --case Q02 --case Q10 --verbose
python evaluation/run_eval.py --json exports/eval.json --min-pass-rate 0.9
```

Run in deterministic mode to gate a release. It is reproducible, so a
regression is a real regression rather than model variance. Run with a provider
configured to check that the model path has not degraded.

Exits non-zero below the pass-rate threshold, so it drops into CI unchanged.

---

## Current results

Deterministic mode, all 14 cases:

```
pass rate          100.0%  (14/14)
groundedness       100.0%
tool recall        100.0%
citation validity  100.0%
content coverage   100.0%
refusal accuracy   100.0%
median latency        74 ms
p95 latency         4537 ms
```

The p95 is the sensitivity analysis, which runs 500 re-scorings. It was 55
seconds before the scoring path was split into a weight-independent ranking
pass and a weight-dependent combination.

---

## What the results do not prove

**Groundedness checks presence, not correct use.** The verifier confirms every
number in the answer appears in the evidence. It cannot detect a number
correctly quoted but attributed to the wrong space, or a real figure used to
support a conclusion it does not support. That needs human review.

**Content coverage is keyword matching.** An answer containing the word
"cilnidipine" passes the check for Q01. Whether the reasoning around it is
sound is not testable this way.

**Fourteen cases is a smoke test, not a benchmark.** They cover the four case
questions and the failure modes the system was built to prevent. They do not
establish general capability.

**Deterministic mode measures the floor.** It exercises the planner, the tools,
the guardrails and the renderer, but not the model's judgement about which
extra tools to call or how to weigh a novel trade-off.

---

## Adding a case

```yaml
- id: Q15
  question: Your question here
  intent: prioritisation          # optional, checked if present
  required_tools: [rank_opportunity_spaces, cipla_portfolio]
  must_include: [statins]         # case-insensitive substrings
  must_not_include: [saroglitazar]
  min_length: 300
  notes: >-
    Why this case exists and what regression it prevents.
```

For a refusal case, set `expect_refusal: true` and omit the rest.

Write the `notes` field. A case without a stated reason becomes untouchable six
months later, because nobody can tell whether a failure is a regression or a
change in intent.
