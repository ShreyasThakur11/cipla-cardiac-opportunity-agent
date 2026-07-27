---
title: User guide
layout: default
nav_order: 9
---

# User guide

Three ways in: a command line, a browser console, and an HTTP API. All three
read the same analysis context, so they cannot disagree with each other.

---

## Command line

### Ask a question

```bash
cardiac-agent ask "Which two or three opportunity spaces should Cipla prioritise?"
cardiac-agent ask "Is the growth in Other Lipid Reducers accessible to Cipla?" --trace
cardiac-agent ask "How big is the ezetimibe franchise?" --evidence --json
```

`--trace` prints the execution record: which tools ran, what the guardrails
decided, how long each stage took. `--evidence` prints the raw tool results, so
any figure in the answer can be traced to its source.

### Look at the scorecard directly

```bash
cardiac-agent rank --level sub_segment --by cipla_priority_score --top 10
cardiac-agent rank --level molecule_combination --by market_opportunity_index
cardiac-agent rank --level anchor_molecule --top 15
```

Ranking by `market_opportunity_index` answers "what is attractive". Ranking by
`cipla_priority_score` answers "what should Cipla do". They give different
answers, and the difference is the analysis.

### The other commands

```bash
cardiac-agent whitespace                       # underpenetrated spaces with a route in
cardiac-agent sensitivity --level sub_segment --top-k 3
cardiac-agent export                           # CSV + JSON for the deck
cardiac-agent doctor                           # health check
cardiac-agent build --force                    # rebuild the warehouse
cardiac-agent serve --port 8000                # run the API
```

---

## Streamlit console

```bash
streamlit run src/cardiac_agent/ui/streamlit_app.py
```

Five tabs, in the order the case asks its questions.

**Overview.** Market size, and the split between reported growth, real demand
growth and volume. The bar chart comparing the three across segments is the
fastest way to see which apparent winners are price stories.

**Prioritisation.** The two-axis chart: opportunity on the vertical, right to
win on the horizontal, bubble size the market value, quadrant lines at 70. The
top-right quadrant is where to spend; the top-left is where somebody else will
win. Switch the ranking between the two scores with the radio control, and open
the expander for rank stability under 500 randomised weightings.

**Deep dive.** An evidence card for any single space: size and growth split
into demand and price, competitive structure, the leading players, the score
decomposition by pillar, and the external signals attached with the tilt they
produced.

**Whitespace and forecast.** Underpenetrated spaces with the route in spelled
out, then three-to-five year projections plotted against current size with the
market rate marked.

**Ask the agent.** Free text, with example questions prefilled. Every answer
shows whether numeric grounding passed, the sources cited, the full execution
trace and the evidence pack.

The sidebar always shows the data lineage: source filename, SHA-256 prefix,
build timestamp and row count. If a figure on screen is ever questioned, that
is where the answer starts.

---

## HTTP API

```bash
cardiac-agent serve
# interactive documentation at http://localhost:8000/docs
```

### Agent

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which spaces should Cipla prioritise?", "include_trace": true}'
```

Returns the answer, the citations, the tools used, whether the deterministic
renderer was involved, any warnings, and the trace.

### Analytics

These skip the model entirely and return in milliseconds.

```bash
curl http://localhost:8000/analytics/overview
curl -X POST http://localhost:8000/analytics/rank \
  -H "Content-Type: application/json" \
  -d '{"level": "molecule_combination", "rank_by": "market_opportunity_index", "top_n": 5}'
curl http://localhost:8000/analytics/space/MOL_C02F0O_CILNIDIPINE_TELMISARTAN
curl http://localhost:8000/analytics/whitespace?limit=10
curl http://localhost:8000/analytics/competitor/Torrent
curl -X POST http://localhost:8000/analytics/forecast \
  -H "Content-Type: application/json" \
  -d '{"space": "ROSUVASTATIN + EZETIMIBE", "horizon_years": 5}'
curl -X POST http://localhost:8000/analytics/sensitivity \
  -H "Content-Type: application/json" \
  -d '{"level": "sub_segment", "top_k": 3}'
```

### Signals

```bash
curl -X POST http://localhost:8000/signals/search \
  -H "Content-Type: application/json" \
  -d '{"query": "ezetimibe guidelines", "top_k": 3}'
curl http://localhost:8000/signals/citations     # the appendix, as JSON
```

Set `CARDIAC_API_KEY` in `.env` to require an `X-API-Key` header on `/agent`
and `/analytics`.

---

## Python

```python
from cardiac_agent.agent import build_agent
from cardiac_agent.pipeline import get_context

context = get_context()
print(f"{context.totals['market_value_t2']:,.0f} crore")

top = context.scored[context.scored["level"] == "molecule_combination"]
print(top.nlargest(5, "cipla_priority_score")[["space_label", "cipla_priority_score"]])

agent = build_agent(context)
result = agent.ask("Which spaces are underpenetrated by Cipla?")
print(result.answer)
print(result.state.to_trace())
```

---

## Reading the output

**Growth figures.** Three of them, and the differences matter more than the
levels. Reported growth moves on price and demand together. Real growth holds
prices at the prior year, so it is demand. Volume growth confirms it. When
reported growth is much higher than real growth, the space is being repriced
rather than growing.

**HHI.** Below 1,500 is fragmented, 1,500 to 2,500 moderately concentrated,
above 2,500 concentrated. Read it alongside leader share: three players at 20
per cent each is a different market from one at 60 per cent, despite similar
combined share.

**Penetration index.** Cipla's share of a space divided by its 1.68 per cent
share of the therapy area. Below 100 means underweight; 11 means Cipla holds
about a ninth of what its overall position would imply.

**Trend multiplier.** The external-signal tilt, bounded to 0.80 to 1.25 and
centred within each level. A value near 1.00 does not mean no signals attached;
it means the signals that attached apply about as much to this space as to
everything else at its level.

**Top-k frequency.** How often a space stayed in the top K across 500
randomised weightings. Above 0.80 the recommendation survives almost any
reasonable framework; below 0.60 it is a judgement call.

---

## Questions worth asking

Straightforward:

- What are the top opportunity spaces at the molecule-combination level?
- Which two or three should Cipla actively prioritise, and why those?
- Which attractive spaces are underpenetrated by Cipla today?
- Where should Cipla double down, build capability, be selective, or avoid?

Sharper, and better at exposing whether the analysis holds:

- Which spaces are growing on price rather than demand?
- Is the growth in Other Lipid Reducers actually accessible to Cipla?
- Cipla holds 24 per cent of fibrates. Why is that not a priority?
- Which molecule franchises span several sub-segments, and how large are they?
- How would the ranking change if size mattered less and growth mattered more?
- Where is Cipla's largest position, and is that space still growing in real
  terms?

The agent will refuse anything outside the dataset, and will decline to
recommend a space it judges structurally closed even when the growth number is
the highest on the page.
