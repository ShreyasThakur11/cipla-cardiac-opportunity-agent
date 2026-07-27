# Cardiac Opportunity Agent

[![Licence: MIT](https://img.shields.io/badge/licence-MIT-lightgrey.svg)](LICENSE)

An AI agent that reads the India Cardiac prescription audit, fuses it with a
cited corpus of external signals, and ranks the opportunity spaces where Cipla
has a sustainable right to win over the next three to five years.

Built for Ascend Season 4 (2026), case study *AI-Enabled Prioritization with
Integrated Trend Analytics*.

**[Documentation](https://shreyasthakur11.github.io/cipla-cardiac-opportunity-agent/)**
· [Case answers](docs/case-answers.md)
· [Framework](docs/PRIORITIZATION_FRAMEWORK.md)
· [Architecture](docs/ARCHITECTURE.md)
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

No analytical constant is hard-coded. Every weight, threshold and forecast
assumption lives in `config/settings.yaml`, so a challenge to any assumption is
answered by editing one number and re-running.

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

`POST /agent/ask` runs the reasoning loop and spends tokens. `/analytics/*`
returns the same analysis in milliseconds for nothing. Interactive schema at
`/docs`.

<br>

## Verification

```
Golden question set                     Other gates
──────────────────────────────          ──────────────────────
pass rate          100.0%  (14/14)      150 tests passing
groundedness       100.0%               ruff clean
tool recall        100.0%               deck geometry clean
citation validity  100.0%               house style clean
content coverage   100.0%
refusal accuracy   100.0%
median latency        74 ms
```

The golden set covers all four case questions and the failure modes this system
exists to prevent, including a trap question about a high-growth,
originator-held space. Nothing is scored by another language model. Every
measure is a deterministic assertion against the run.

```bash
pytest                            # 150 tests
python evaluation/run_eval.py     # golden set
python scripts/check_deck.py      # slide geometry
python scripts/check_prose.py     # house style across every text file
```

<br>

## Data confidentiality

The Cardiac dataset and the case PDF are licensed material supplied by the
organisers. They are excluded from version control and must not be committed.
The build records a SHA-256 of the workbook, so any result ties back to the
input that produced it.

<br>

## Licence

MIT, covering the source code only. See [LICENSE](LICENSE). The dataset and
everything derived from it stay under the organisers' terms, which
[NOTICE](NOTICE) sets out.
