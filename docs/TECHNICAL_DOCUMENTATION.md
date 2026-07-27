---
title: Technical reference
layout: default
nav_order: 10
---

# Technical documentation

Module reference and extension points. For the reasoning behind the design see
[ARCHITECTURE.md](ARCHITECTURE.html); for the maths see
[PRIORITIZATION_FRAMEWORK.md](PRIORITIZATION_FRAMEWORK.html).

---

## Package layout

```
src/cardiac_agent/
├── config.py              Settings (env) and FrameworkConfig (YAML)
├── logging_config.py      Structured JSON logging with trace correlation
├── pipeline.py            AnalysisContext: the single source of truth
├── cli.py                 Typer command line
├── ingestion/             workbook -> DuckDB
├── analytics/             every computed number
├── rag/                   corpus, retrieval, signal linking
├── agent/                 graph, nodes, tools, prompts, memory, LLM
├── guardrails/            scope, grounding, citations, injection
├── api/                   FastAPI service
└── ui/                    Streamlit console
```

---

## Configuration

Two sources, deliberately separated.

`config/settings.yaml` holds the analytical parameters, so they are reviewable
and editable by someone who does not write Python. Environment variables, via
`.env`, hold deployment concerns.

```python
from cardiac_agent.config import get_settings, get_framework

settings = get_settings()          # cached Settings instance
framework = get_framework()        # cached FrameworkConfig

framework.get_path("scoring.moi_weights")       # returns None if absent
framework.require("scoring.moi_weights")        # raises KeyError if absent
```

`Settings.llm_available` is the gate the whole system uses to decide whether a
model can be called. It is false when the provider is `none` or no credential
is present, and the agent degrades to the deterministic renderer.

---

## AnalysisContext

The central object. Reads the warehouse, derives every metric, links signals
and scores. Built once per process and cached, because the chain is
deterministic and takes a couple of seconds.

```python
from cardiac_agent.pipeline import get_context

context = get_context()             # cached
context = get_context(refresh=True) # after a rebuild

context.scored          # 108 scored spaces with every metric
context.enriched        # all 326 spaces before filtering
context.totals          # therapy-area totals
context.corpus          # loaded signals
context.retriever       # hybrid retriever
context.find_space("CILNIDIPINE + TELMISARTAN")   # fuzzy lookup
context.space_signals("MOL_C02F0O_CILNIDIPINE_TELMISARTAN")
context.citations()     # appendix-ready
```

If a number is not reachable from an `AnalysisContext`, the agent has no way to
produce it. That is the property the numeric guardrail depends on.

---

## Ingestion

```python
from cardiac_agent.ingestion import build_warehouse
metadata = build_warehouse()        # returns row counts, totals, source digest
```

`load_cardiac_workbook` raises `WorkbookSchemaError` with a named list of
missing columns rather than failing deep inside the loader. If the organisers
reissue the file with different period labels, update `REQUIRED_COLUMNS` in
`excel_loader.py` and the `market.periods` block in `settings.yaml` together.

### Adding a space level

1. Add a block to `_membership_frame` in `spaces.py` producing `(row_id, level,
   space_label, space_id, segment, sub_segment)`.
2. Add the level name to `SPACE_LEVELS` and a description to
   `LEVEL_DESCRIPTIONS`.
3. Add it to `SPACE_LEVELS_ENUM` in `agent/tools.py` so the agent can select it.

Aggregation, competition, right to win and scoring all work off the membership
frame, so nothing else needs to change.

---

## Analytics

```python
from cardiac_agent.analytics import (
    add_growth_metrics, add_competition_metrics, add_right_to_win_metrics,
    build_scorecard, forecast_space, run_sensitivity, find_whitespace,
)
```

The chain is `add_growth_metrics` then `add_competition_metrics` then
`add_right_to_win_metrics` then `build_scorecard`, and each returns a copy
rather than mutating.

### The scoring split

`scoring.py` separates a weight-independent ranking pass from the
weight-dependent combination:

```python
percentiles = metric_percentiles(frame, framework)              # expensive, once
scores = score_from_percentiles(percentiles, framework, weights) # cheap, per iteration
```

`build_scorecard` accepts a pre-computed `percentiles` argument, which is how
the sensitivity analysis runs 500 re-scorings in about four seconds instead of
a minute. `tests/test_scoring.py::TestLeanScoringPath` asserts the two paths
produce bit-identical results, because a divergence would mean the reported
robustness measured a different framework from the one being presented.

### Adding a metric

1. Compute the column in `metrics.py`, `competition.py` or `rightowin.py`.
2. Map the config name to the column in `METRIC_COLUMNS` in `scoring.py`.
3. Add it to `INVERTED_METRICS` if lower is better.
4. Add it to the relevant pillar block in `settings.yaml`, keeping the block
   summing to 1.0. The run fails loudly if it does not.

---

## Retrieval

```python
from cardiac_agent.rag import load_corpus, SignalRetriever, link_signals_to_spaces

corpus = load_corpus()
retriever = SignalRetriever(corpus)
hits = retriever.search("ezetimibe guidelines", top_k=5)
spaces, links = link_signals_to_spaces(spaces, corpus, sku_facts=..., membership=...)
```

### Adding a signal

Create `data/external/signals/S-15-your-topic.md`:

```markdown
---
id: S-15
title: One-line summary
category: guidelines            # groups for within-category damping
publisher: Who published it
source: Full reference
url: https://...                # or internal:// for derived analysis
published: 2025
accessed: 2026-07-26
confidence: high                # high | medium | low
direction: tailwind             # tailwind | headwind | neutral
magnitude: 0.12                 # before confidence weighting
applies_to:
  molecules: [EZETIMIBE]
  sub_segments: ["Statins Comb."]
  keywords: [ezetimibe, ldl]
---

# Body

What the signal says, and a "why this matters for prioritisation" section
explaining how it should change a decision.
```

Scope it as narrowly as the evidence supports. A signal listing sub-segments
tilts every space in them, which is right for a guideline about combination
therapy generally and wrong for one about a specific molecule. That mistake was
made and corrected during development; the fix is in the comment in
`S-11-cilnidipine-fourth-generation-ccb.md`.

### Adding a dense ranker

```python
class MyRanker:
    def rank(self, query, chunks, top_k): ...

retriever.register_dense_ranker(MyRanker())
```

It joins BM25 and trigrams as a third input to reciprocal rank fusion. No
caller changes.

---

## Agent

```python
from cardiac_agent.agent import build_agent
agent = build_agent()
result = agent.ask("Which spaces should Cipla prioritise?")

result.answer          # prose
result.citations       # appendix records
result.evidence        # every tool result
result.state.to_trace()
```

### The graph

`NODES` maps names to functions. Each takes the shared `AgentState` plus
context, tools and llm as keyword arguments, mutates the state, and returns the
name of the next node or `"END"`.

```python
def my_node(state, context, **_) -> str:
    state.node_path.append("my_node")
    ...
    return "synthesize"

NODES["my_node"] = my_node
```

`MAX_TRANSITIONS` caps the loop at 24 so a mis-specified edge cannot spin.

### Adding a tool

In `agent/tools.py`:

```python
def my_analysis(context: AnalysisContext, threshold: float = 1.0) -> dict:
    """Return structured evidence, never prose."""
    ...

ToolSpec(
    name="my_analysis",
    description=(
        "What it returns, and when to reach for it. A description that "
        "only says what a tool is, without saying when to reach for it, is the "
        "main cause of wrong tool selection."
    ),
    input_schema={
        "type": "object",
        "properties": {"threshold": {"type": "number", "minimum": 0}},
        "required": [],
    },
    handler=lambda **kw: my_analysis(context, **kw),
)
```

Then add the name to `agent.enabled_tools` in `settings.yaml`. Removing a name
from that list disables the capability at runtime without touching code.

Raise `ToolError` for bad arguments; the graph turns it into a `tool_result`
with `is_error: true` so the model can recover rather than the run dying.

### Prompts

Markdown files in `agent/prompts/`, loaded by stem and cached. They live as
files rather than string literals so a reviewer can read and edit the agent's
instructions without touching Python, and so prompt changes appear as readable
diffs.

### LLM layer

`build_llm_client()` returns `AnthropicClient`, `OpenAIClient` or `NullClient`.
A missing key or an uninstalled SDK downgrades to `NullClient` with a warning
rather than raising, so a demonstration never dies on a credential problem.

Anthropic specifics the code depends on: Claude Opus 5 rejects `temperature`,
`top_p` and `top_k`; thinking is adaptive and `budget_tokens` is removed; a
request can return `stop_reason == "refusal"` with a normal 200, so the client
checks that before reading content. The system prompt is marked for prompt
caching because it is large and re-sent on every turn of the tool loop.

---

## Guardrails

```python
from cardiac_agent.guardrails import check_scope, run_output_guardrails

decision = check_scope(question)
outcome = run_output_guardrails(draft, evidence, known_signal_ids)
```

`collect_numbers` walks any structure, including numbers embedded in strings,
and records both the ratio and percentage form of each value so `0.284` in the
evidence matches `28.4%` in the prose.

To tune the numeric check, edit `guardrails.numeric_tolerance` and
`numeric_ignore_below` in `settings.yaml`. To add a structural pattern that
should never count as a numeric claim, add it to `_STRIP_PATTERNS` in
`numeric_grounding.py`, as was done for ATC codes and identifiers like
`NFHS-5`.

---

## Logging

Every line is a JSON object with a `trace_id`, so one agent run can be
reconstructed from the log alone.

```python
from cardiac_agent.logging_config import get_logger, new_trace_id
logger = get_logger(__name__)
logger.info("my.event", space_id="MOL_X", value=759.4)
```

Useful event names when debugging: `agent.plan`, `agent.tool.rejected`,
`guardrail.numeric_grounding`, `guardrail.scope.hard_block`, `linker.done`,
`sensitivity.done`, `warehouse.built`.

---

## Performance

| Operation | Time |
| --- | --- |
| Build warehouse | ~4 s |
| Build analysis context | ~2 s |
| Deterministic answer | 20 to 150 ms |
| Sensitivity, 500 iterations | ~4 s |
| Answer with a model | 5 to 30 s, dominated by the provider |

The context is cached per process, so only the first request pays the build.
The API builds it at startup for the same reason.
