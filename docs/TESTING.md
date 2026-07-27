---
title: Testing
layout: default
nav_order: 15
---

# Testing

## Strategy

Two layers, with different jobs.

**Unit and integration tests** (`pytest`, 150 tests) verify the maths, the
guardrails and the plumbing. Most run against a small synthetic market built in
memory, so they are fast, hermetic, and runnable on a fresh clone without the
competition dataset. Expected values are computed by hand in the assertions
rather than by calling the code under test, so a change in the implementation
cannot silently redefine what a metric means.

**The golden set** (`evaluation/run_eval.py`) verifies end-to-end behaviour.
See [EVALUATION.md](EVALUATION.html).

---

## Running

```bash
pytest                                    # everything
pytest -m "not requires_data"             # no warehouse needed
pytest tests/test_guardrails.py -v        # one file
pytest --cov=cardiac_agent --cov-report=term-missing
```

Tests needing the warehouse are marked `requires_data` and skip cleanly when it
has not been built.

---

## What is covered

### `test_ingestion.py`

Molecule splitting, including the cases that are easy to get wrong: stacked
qualifiers (`ROSUVASTATIN CALCIUM SALT` reduces to `ROSUVASTATIN` only after two
passes) and nitrate esters, which must **not** reduce because isosorbide
mononitrate and dinitrate are different drugs rather than salt forms of one.

Brand root recovery against real names, including the negative case:
`ACE REVELOL` must not reduce to `ACE`, because `REVELOL` is a brand rather than
a line-extension modifier.

Space construction, including an explicit test that anchor-molecule values sum
to **more** than the market. That is intended behaviour, and asserting it stops
somebody "fixing" it later.

### `test_metrics.py`

Every growth formula, with hand-computed expectations. The most important is
`test_real_growth_uses_constant_prices_against_prior_reported`: the glossary
defines MAT CP at the prior year's price level, so real growth is MAT CP for
the latest period against **reported** MAT for the prior period, not against
prior-period MAT CP. Getting this wrong would misstate the price contribution
across the entire analysis and would not be visible in any output.

Also: price-led growth is detectable (value up, constant price flat, the gap
shows as price), zero denominators do not explode, growth is clipped, and
market totals use only the segment level so no double counting occurs.

### `test_scoring.py`

Configured weights sum to 1.0 and a block that does not is rejected. Scores are
bounded. Priority never exceeds opportunity, because the gate is a multiplier
capped at 1.0. The gate curve bends below linear.

`TestLeanScoringPath::test_matches_the_full_path_exactly` asserts that the fast
path used by the sensitivity loop produces bit-identical results to
`build_scorecard`. If those diverge, every stability number reported to a jury
would be measuring a different framework from the one being presented.

Sensitivity is reproducible from a fixed seed, because a robustness figure that
moves between runs is noise rather than evidence.

### `test_guardrails.py`

The most important file in the suite. Numeric grounding accepts a grounded
answer, rejects a fabricated number, tolerates rounding, and ignores years, ATC
codes, citation markers and identifiers such as `NFHS-5`. That last case is a
regression test: the "5" in "NFHS-5" was being read as an unsupported numeric
claim.

Citations reject an invented `[S-99]` and flag an unsourced external claim
without failing the answer. Scope allows in-scope questions including
strategy-vocabulary ones with no molecule named, refuses hard blocks such as
share price, allows a cross-therapy framing question, and refuses instruction
override without leaking the prompt.

### `test_rag.py`

Signal semantics (direction, confidence weighting, internal labelling), corpus
integrity (every signal has a source and a publisher, identifiers are unique),
retrieval (finds the right signal, one passage per signal, survives a
misspelling), and linking.

Two linking tests carry the design:
`test_differential_evidence_moves_the_ranking` and
`test_universal_evidence_moves_nothing`. The second asserts that a signal
applying to every space produces an identical multiplier everywhere, which is
what the centring step exists to guarantee.

### `test_agent.py`

Prompts load and state the core rule. Intent classification routes each case
question correctly, including `test_sensitivity_wins_over_ranking`, which
prevents the regression described in [EVALUATION.md](EVALUATION.html).

Tool schemas are checked for descriptions longer than 60 characters, on the
basis that a description saying only what a tool is, without saying when to
reach for it, is the main cause of wrong tool selection.

SQL injection defence is parameterised over six mutating statements, including
a stacked `SELECT 1; DROP TABLE`.

End-to-end: the agent answers, refuses, produces a complete trace, gives
identical answers to identical questions in deterministic mode, and every
number in its output passes the grounding check.

API: health, ranking, a 422 on an invalid level, a 404 on an unknown space,
and appendix-ready citations.

---

## Conventions

**Hand-computed expectations.** `assert out["value_yoy"] == pytest.approx(150.0
/ 120.0 - 1.0)`, not a comparison against another call to the same function.

**Behaviour, not implementation.** Tests assert what a metric means, so a
refactor that preserves meaning does not break them.

**Regression tests carry their reason.** Every test that exists because of a
specific bug says so in its docstring, so a future reader knows whether a
failure is a regression or a deliberate change.

**Negative cases matter as much as positive ones.** `ACE REVELOL` not reducing,
isosorbide esters not merging, universal signals not tilting, priority not
exceeding opportunity.

---

## Not covered

- **Live model behaviour.** No test makes a paid API call. The model path is
  exercised in deterministic mode through `NullClient`, which drives the same
  graph.
- **Streamlit rendering.** Manually verified. The logic it displays is tested
  through the same context object.
- **Load and concurrency.** Not a production service.
- **The analysis being correct.** The tests verify that the framework computes
  what it says it computes. Whether the framework is the right framework is a
  judgement the sensitivity analysis bounds and human review has to make.
