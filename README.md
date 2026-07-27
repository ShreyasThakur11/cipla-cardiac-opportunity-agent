<div align="center">

# Cardiac Opportunity Agent

[![CI](https://github.com/ShreyasThakur11/cipla-cardiac-opportunity-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ShreyasThakur11/cipla-cardiac-opportunity-agent/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-lightgrey.svg)](LICENSE)

</div>

<br>

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

Every figure comes from a deterministic engine. The model plans, calls tools,
and writes prose over a finished evidence pack. A verifier then matches every
number in the draft against that pack and rejects what it cannot trace.

The scorecard is therefore reproducible byte for byte, and the system answers
correctly with no API key.

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
pip install -e .
```

Copy the workbook to `data/raw/cardiac_dataset.xlsx`. It is licensed material
and stays out of version control; see [`data/raw/README.md`](data/raw/README.md).

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
```

<br>

## Verification

14 of 14 golden questions pass, at 100 per cent on groundedness, citation
validity and refusal accuracy, alongside 150 tests. Nothing is scored by another
language model.

[How it is measured](docs/EVALUATION.md)

<br>

## Licence

MIT for the source code. The dataset and everything derived from it stay under
the organisers' terms.

[LICENSE](LICENSE) · [NOTICE](NOTICE)
