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

## Run it

Each block is one step. Use the copy button on the block, paste into a
terminal, press enter. Python 3.10 or newer is the only prerequisite.

**1. Get the code**

```bash
git clone https://github.com/ShreyasThakur11/cipla-cardiac-opportunity-agent.git
cd cipla-cardiac-opportunity-agent
```

**2. Create an environment and install**

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

**3. Add the data**

Copy the competition workbook to `data/raw/cardiac_dataset.xlsx`. It is
licensed material, so it is not in this repository and must never be committed;
see [`data/raw/README.md`](data/raw/README.md).

**4. Build the warehouse and check the installation**

```bash
cardiac-agent build
cardiac-agent doctor
```

`doctor` ends with `All checks passed.` when everything is in place.

**5. Open the console**

```bash
streamlit run src/cardiac_agent/ui/streamlit_app.py
```

The browser opens at `localhost:8501` with five tabs following the case
questions: the market, the ranking, whitespace, forecasts and a free-form Ask
tab.

No API key is required at any step. Without one, every answer is rendered
deterministically and every number is identical. For narrated prose, copy
`.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

<br>

## Ask from the terminal

The same analysis without the console:

```bash
cardiac-agent ask "Which two or three opportunity spaces should Cipla prioritise?"
```

```bash
cardiac-agent rank --level molecule_combination
```

```bash
cardiac-agent whitespace
```

```bash
cardiac-agent sensitivity --level sub_segment
```

`cardiac-agent serve` runs the REST API on port 8000, with the interactive
schema at `/docs`. The [user guide](docs/USER_GUIDE.md) covers every command
and flag.

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
