---
title: Architecture
layout: default
nav_order: 6
---

# Architecture

## The organising principle

Two things have to be true at once. The system must reason flexibly enough to
answer a question nobody anticipated, and every number it produces must be
exactly reproducible and traceable to a source.

Those requirements pull in opposite directions if you ask one component to
satisfy both. So they are separated:

- **A deterministic analytics engine** computes every figure. Pure Python over
  a DuckDB warehouse. No model involved, same input to same output, always.
- **A language model** plans, selects tools and writes prose about a finished
  evidence pack. It never calculates.
- **A verifier** stands between them, extracting every number from the draft
  answer and checking it against the evidence before release.

Everything else follows from that split.

---

## Data flow

```
                         config/settings.yaml
                                  │
                                  ▼
 Cardiac workbook ──▶ ingestion ──▶ DuckDB warehouse ──▶ analytics ──▶ AnalysisContext
   (7,452 SKUs)      validate       6 tables +           metrics,        108 scored
                     normalise      SHA-256 of source     competition,     spaces
                     build spaces                         right to win,
                                                          scoring,
 data/external/                                           forecast,
  signals/*.md ──▶ RAG corpus ──▶ hybrid retrieval ─────▶ sensitivity
   (14 cited)      front matter    BM25 + trigram          ▲
                   + body          + RRF                   │
                        └──▶ signal-to-space linker ───────┘
                                  bounded, centred
                                                                 │
                                                                 ▼
   question ──▶ scope gate ──▶ planner ──▶ tools ──▶ evidence pack
                    │                                      │
                    │                                      ▼
                    │                            LLM synthesises draft
                    │                                      │
                    │                                      ▼
                    │                      numeric grounding + citation check
                    │                                │            │
                    │                             passes        fails
                    │                                │            │
                    ▼                                ▼            ▼
                refusal                           answer     rewrite once,
                                                             then deterministic
                                                             renderer
```

---

## Components

### Ingestion (`src/cardiac_agent/ingestion/`)

| Module | Responsibility |
| --- | --- |
| `excel_loader.py` | Read both worksheets, assert the 30 required columns, coerce numerics, fail with a named list rather than a stack trace |
| `normalize.py` | Derive molecule tokens, treatment archetype, brand root, focal-company flag |
| `spaces.py` | Build the six space levels and the SKU-to-space membership map |
| `build_warehouse.py` | Persist to DuckDB and parquet, record a SHA-256 of the source |

Four derivations carry the analysis. Molecule tokenisation splits combination
strings and strips salt suffixes, so "AMLODIPINE BESILATE + ATENOLOL" becomes
two ingredients and the amlodipine franchise can be summed across every pack
that contains it. Treatment archetype classifies packs by how many actives the
prescriber is buying. Brand root recovers the umbrella name from a line
extension, which is what makes "can Cipla extend an existing brand into this
space" a measurable question rather than a judgement. And the focal flag
identifies Cipla's rows for the right-to-win pillar.

**Why DuckDB.** The agent is allowed to run ad-hoc SQL when a question does not
fit a pre-built tool. Handing a model a real query engine on a read-only
connection is safer and far more expressive than letting it construct pandas
expressions, and DuckDB needs no server, no credentials and no container. It is
one file next to the code. A parquet mirror is written alongside so the
warehouse is readable from Excel, R or a notebook without a DuckDB dependency.

### Analytics (`src/cardiac_agent/analytics/`)

| Module | Responsibility |
| --- | --- |
| `metrics.py` | Growth, real (constant-price) growth, volume, price effect, momentum, focal position |
| `competition.py` | HHI, player count, leader and top-three share, crowding, share churn, new entrants |
| `rightowin.py` | The six right-to-win components, from Cipla's actual estate |
| `scoring.py` | Percentile normalisation, four pillars, Market Opportunity Index, right-to-win gate, Cipla Priority Score |
| `forecast.py` | Three-to-five year projection with mean reversion and a scenario band |
| `sensitivity.py` | Rank stability under 500 randomised weightings |
| `whitespace.py` | Attractive spaces where Cipla is underweight but has a route in |

Normalisation is percentile rank **within a level**. Comparing a three-member
segment against a hundred-and-fifty-member molecule list on a common min-max
scale would say more about the size of the list than about the market.
Percentile rank is also robust to the heavy skew in pharmaceutical audit data,
where a handful of molecules carry most of the value.

The scoring module is split into a weight-independent ranking pass
(`metric_percentiles`) and a weight-dependent combination
(`score_from_percentiles`). That split is what makes 500 sensitivity iterations
run in about four seconds rather than a minute, and a test asserts the two
paths produce bit-identical results.

### Retrieval (`src/cardiac_agent/rag/`)

Fourteen curated markdown documents with YAML front matter declaring what each
signal applies to, which direction it pushes, how strongly and how much it is
trusted. Ten are external publications; four are analysis of the supplied
dataset, labelled as such.

Retrieval fuses BM25 over word tokens with cosine similarity over character
trigrams, combined by reciprocal rank fusion. BM25 is precise on exact
terminology, which is most of what gets asked in a domain this dense with drug
names; trigrams catch morphological variants and near-misses that BM25 drops.
RRF needs no score calibration between the two, because it uses positions only.

**Why not a transformer embedding index.** The corpus is a few dozen chunks of
carefully written technical text. Dense retrieval earns its keep on large noisy
corpora where vocabulary mismatch dominates; here it would add an API
dependency, a model download and a source of run-to-run variation for little
measurable gain. `SignalRetriever.register_dense_ranker` accepts a third ranker
without touching callers if that changes.

The **linker** is the join between the case's two halves. It maps signals onto
spaces by molecule, sub-segment, segment or keyword and produces a bounded
`trend_multiplier`. Three rules keep it honest: confidence discounts magnitude,
within a category the strongest signal counts fully and the rest at half
weight, and the resulting tilt is **centred on the median tilt of its level**.
That last rule matters most. Several signals apply to nearly every space;
uncentred they would add the same constant everywhere and push every multiplier
into the ceiling, turning a discriminating input into a flat one. Centred, a
signal that applies to everything moves nothing, and only differential evidence
changes the ranking.

### Agent (`src/cardiac_agent/agent/`)

A state machine with six nodes and two conditional edges:

```
scope ──▶ plan ──▶ gather ──▶ synthesize ──▶ verify ──▶ finalise
  │                                             │
  └── END (refusal)                             └── verify (one rewrite)
```

The **plan** node does two jobs. It classifies the question into one of ten
intents and schedules a baseline set of tool calls, then lets the model add to
that set. The baseline is what guarantees the agent gathers the right evidence
even when the model chooses badly, and it is what makes the no-credentials path
work at all.

Eleven tools, each a thin wrapper over the analytics engine. None takes a
free-text instruction that could change a calculation, and none returns prose.
The union of their results is the complete set of figures the agent may state,
which is the property that makes the numeric guardrail enforceable.

**Why not LangGraph.** The graph abstraction is right for this problem; the
dependency is not. LangGraph would bring LangChain's transitive tree into a
project whose entire model surface is one `messages.create` call, add a
version-compatibility risk to a system that has to run reliably in front of a
panel, and hide the control flow behind a builder API. What it would give back,
checkpointing and streaming and human-in-the-loop interrupts, this agent does
not use. Roughly a hundred lines of explicit dispatch buys the same semantics,
runs offline, and can be read end to end in one sitting. The node signatures
are already the shape LangGraph expects if durable cross-process execution ever
becomes a requirement.

### Guardrails (`src/cardiac_agent/guardrails/`)

| Check | When | On failure |
| --- | --- | --- |
| Scope | Before any tool runs | Refuse, and explain what the agent does cover |
| Prompt injection | On retrieved text | Neutralise the span and wrap the result as data |
| Numeric grounding | On the draft | Reject, feed back the specific numbers, rewrite once |
| Citations | On the draft | Reject an unresolvable `[S-xx]`; warn on an unsourced external claim |

Scope runs first so an out-of-scope question costs nothing and cannot
contaminate the transcript with retrieved material that was never relevant.

Numeric grounding is the load-bearing one. Because every legitimate figure came
from a tool result, the union of the tool results is the allowed set. The check
extracts every number from the draft, ignores structural ones (years, ATC
codes, citation markers, identifiers such as NFHS-5) and anything below a small
floor, then matches each remaining number against the allowed set within a two
per cent relative tolerance. A percentage matches both the raw ratio and the
ratio times one hundred.

### Delivery

**CLI** (`cli.py`) for the fastest path to an answer and for the evaluation
suite. **FastAPI** (`api/`) with the heavy objects built once at startup, so
no request pays the build cost. **Streamlit** (`ui/`) as the presentation
console, rendering from the same `AnalysisContext` the CLI and API use, so what
is on screen cannot drift from what the agent answers.

---

## Technology decisions

| Choice | Alternative considered | Reasoning |
| --- | --- | --- |
| DuckDB | SQLite, pandas only, PostgreSQL | Columnar and fast on this shape, zero configuration, and it gives the agent a real query engine on a read-only connection. Postgres would add a service to a system that ships as one file. |
| Explicit state machine | LangGraph, LangChain agents | Same semantics, no transitive dependency tree, control flow readable end to end, and it runs offline. See above. |
| Anthropic Claude, provider-abstracted | OpenAI only, no abstraction | Claude is the default because the loop leans on adaptive thinking and long-context tool use. The abstraction exists mainly so `NullClient` can make the system run with no credentials at all. |
| BM25 plus trigram fusion | ChromaDB, FAISS, pgvector | Fourteen carefully written documents. A vector database would add infrastructure and non-determinism for no measurable retrieval gain at this scale. |
| Percentile normalisation | Min-max, z-score | Audit data is heavily skewed; min-max would let one outlier compress everything else into the bottom decile. |
| Config-driven weights | Constants in code | A jury challenge is answered by editing one YAML value and re-running, not by editing Python. |
| Deterministic renderer fallback | Fail when no model is available | The demonstration cannot die because a key expired. The analysis is identical; only the prose differs. |

---

## Reproducibility

Three mechanisms, all necessary.

**Source provenance.** The build records a SHA-256 of the workbook in
`build_metadata`, so any result ties back to the exact input.

**Configuration provenance.** Every weight, threshold and forecast assumption
is in `config/settings.yaml`, and the weights actually used are attached to
each `ScoreResult` and written into `cardiac-agent export`.

**Seeded randomness.** The only stochastic component is the sensitivity
analysis, seeded from config. A test asserts that two runs produce identical
stability numbers, because a robustness figure that moves between runs is noise
rather than evidence.
