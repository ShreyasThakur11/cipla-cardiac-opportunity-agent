# Cardiac Opportunity Agent

An AI agent that reads the India Cardiac prescription audit, fuses it with a
cited corpus of external signals, and ranks the opportunity spaces where Cipla
has a sustainable right to win over the next three to five years.

Built for Ascend Season 4 (2026), case study *AI-Enabled Prioritization with
Integrated Trend Analytics*.

**[Documentation](https://shreyasthakur11.github.io/cipla-cardiac-opportunity-agent/)**
· [Case answers](docs/case-answers.md)
· [Framework](docs/PRIORITIZATION_FRAMEWORK.md)
· [Decks](deliverables/)

<br>

## The design decision behind everything else

The language model never calculates a number.

Every figure comes from a deterministic engine written in ordinary Python. The
model plans, calls tools, and writes prose over a finished evidence pack. A
verifier then extracts every number from the draft and matches it against that
pack. Anything untraceable is rejected and rewritten.

Two consequences. The scorecard is reproducible byte for byte. And the system
answers correctly with no API key, because the numbers were never the model's
job.

<br>

## What it found

Cipla holds **1.68 per cent** of a **₹23,244 crore** market and grows at
**4.6 per cent** against the market's **13.3 per cent**. It ranks nineteenth of
279 companies.

![Opportunity against right to win](docs/assets/priority-matrix-sub-segment.svg)

The vertical axis rates a space for anybody. The horizontal axis asks whether
Cipla can win it. Separating them is what stops an attractive but inaccessible
space from being recommended.

[Read the answers](docs/case-answers.md)

<br>

## Quick start

```bash
git clone https://github.com/ShreyasThakur11/cipla-cardiac-opportunity-agent.git
cd cipla-cardiac-opportunity-agent

python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

Copy the workbook to `data/raw/cardiac_dataset.xlsx`. It is excluded from
version control by design; see [`data/raw/README.md`](data/raw/README.md).

```bash
cardiac-agent build
cardiac-agent doctor
cardiac-agent ask "Which two or three opportunity spaces should Cipla prioritise?"
```

No API key required. For narrated answers, copy `.env.example` to `.env` and set
`ANTHROPIC_API_KEY`.

<br>

## Interfaces

```bash
streamlit run src/cardiac_agent/ui/streamlit_app.py   # presentation console
cardiac-agent serve                                    # REST API on :8000
cardiac-agent rank --level molecule_combination        # scorecard
cardiac-agent whitespace                               # underpenetrated spaces
cardiac-agent sensitivity --level sub_segment          # rank stability
cardiac-agent export                                   # CSV and JSON for the deck
```

The console has five tabs following the case questions. The API separates the
two costs: `POST /agent/ask` runs the reasoning loop and spends tokens;
`/analytics/*` returns the same analysis in milliseconds for free. Interactive
schema at `/docs`.

<br>

## The agent

```
scope ──▶ plan ──▶ gather ──▶ synthesize ──▶ verify ──▶ finalise
  │                                             │
  └── refuse, out of scope                      └── rewrite once, then fall back
```

Eleven tools, each a thin wrapper over the analytics engine. None accepts a
free-text instruction that could change a calculation, and none returns prose:

`market_overview` · `rank_opportunity_spaces` · `space_deep_dive` ·
`compare_spaces` · `competitor_profile` · `cipla_portfolio` ·
`whitespace_scan` · `forecast_space` · `sensitivity_analysis` ·
`retrieve_external_signals` · `sql_query`

Four guardrails: scope control before any tool runs, numeric grounding and
citation validation on the draft, injection neutralisation on retrieved text.

An explicit state machine rather than LangGraph, for reasons set out in
[Architecture](docs/ARCHITECTURE.md).

<br>

## Opportunity spaces

The case defines a space loosely, so the agent builds every reading of it and
scores them on a common footing.

| Level | What it is | Scored |
| --- | --- | ---: |
| `segment` | Anti-Hypertensives, Lipid Regulators, Anti-Angina | 3 |
| `sub_segment` | ARBs, Statins Comb., AHT Triple / Poly Comb. | 14 |
| `molecule_class` | ATC-4 class | 13 |
| `molecule_combination` | ATC-5 molecule or FDC, the launch-decision level | 45 |
| `treatment_archetype` | Monotherapy, Dual FDC, Triple-or-Poly FDC | 7 |
| `anchor_molecule` | Every pack containing an ingredient, plain or combined | 26 |

Anchor spaces overlap the others deliberately. A Cilnidipine + Telmisartan pack
counts towards both franchises, which exposes clusters no reporting hierarchy
shows. They are ranked separately for that reason.

<br>

## Verification

```
Golden question set                     Other gates
──────────────────────────────          ──────────────────────
pass rate          100.0%  (14/14)      150 tests passing
groundedness       100.0%               ruff clean
tool recall        100.0%               deck geometry clean
citation validity  100.0%
content coverage   100.0%
refusal accuracy   100.0%
median latency        74 ms
```

The golden set covers all four case questions plus the failure modes this system
exists to prevent, including a trap question about a high-growth,
originator-held space.

Nothing is scored by another language model. Every measure is a deterministic
assertion against the run.

```bash
pytest                            # 150 tests
python evaluation/run_eval.py     # golden set
python scripts/check_deck.py      # slide geometry
python scripts/check_prose.py     # house style across every text file
```

<br>

## Layout

```
config/settings.yaml       every weight, threshold and forecast assumption
data/external/signals/     14 cited external signals, one file each
data/raw/                  the workbook (not committed)
src/cardiac_agent/
  ingestion/               workbook to typed DuckDB warehouse
  analytics/               metrics, competition, right to win, scoring,
                           forecasting, sensitivity, whitespace
  rag/                     corpus, hybrid retrieval, signal-to-space linking
  agent/                   graph, nodes, tools, prompts, memory, LLM layer
  guardrails/              scope, numeric grounding, citations, injection
  api/ · ui/ · cli.py      delivery surfaces
scripts/                   chart and deck builders, layout and style checks
evaluation/                golden questions and metrics
tests/                     150 tests
docs/                      the published documentation site
deliverables/              the two presentation decks
```

No analytical constant is hard-coded. Every weight, threshold and forecast
assumption lives in `config/settings.yaml`, so a jury challenge is answered by
editing one number and re-running.

<br>

## Documentation

| | |
| --- | --- |
| [Case answers](docs/case-answers.md) | The four case questions, answered with figures |
| [Prioritisation framework](docs/PRIORITIZATION_FRAMEWORK.md) | Every metric, weight and formula |
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow, technology decisions |
| [Chart gallery](docs/visuals.md) | Every figure, and what it shows |
| [Installation](docs/INSTALLATION.md) | Setup, Docker, troubleshooting |
| [User guide](docs/USER_GUIDE.md) | CLI, console and API walkthroughs |
| [Technical reference](docs/TECHNICAL_DOCUMENTATION.md) | Modules and extension points |
| [Data dictionary](docs/DATA_DICTIONARY.md) | Source columns, derived fields, tables |
| [Assumptions](docs/ASSUMPTIONS.md) | Every judgement call, with its reasoning |
| [Limitations](docs/LIMITATIONS.md) | What this cannot tell you |
| [Evaluation](docs/EVALUATION.md) · [Testing](docs/TESTING.md) | Method and results |
| [Deployment](docs/DEPLOYMENT.md) · [Security](docs/SECURITY.md) | Running it, and the threat model |
| [Slide storyboard](docs/slide-storyboard.md) | What goes on each slide, and why |
| [Appendix of sources](docs/appendix-sources.md) | Every external source |

<br>

## Data confidentiality

The Cardiac dataset and the case PDF are licensed material supplied by the
organisers. They are excluded from version control and must not be committed.
The build records a SHA-256 of the workbook, so any result ties back to the
input that produced it.

<br>

## Licence

MIT, covering the source code only. See [LICENSE](LICENSE).
