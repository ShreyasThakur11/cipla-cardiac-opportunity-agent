---
title: Installation
layout: default
nav_order: 8
---

# Installation

## Requirements

- Python 3.10 or later (3.11 or 3.12 recommended)
- About 500 MB of disk for dependencies, plus roughly 60 MB for the warehouse
- The Cardiac workbook supplied with the case
- No API key is required. One is optional, and only affects prose.

---

## Standard install

```bash
git clone <your-repo-url>
cd cipla-cardiac-opportunity-agent

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

`pip install -e .` puts the `cardiac-agent` command on your path. Without it,
substitute `python -m cardiac_agent.cli` for `cardiac-agent` throughout.

### Place the data

The workbook is licensed material and is excluded from version control.

```bash
# Windows
copy "Data Set_Ascend Season 4_2026.xlsx" data\raw\cardiac_dataset.xlsx
# macOS / Linux
cp "Data Set_Ascend Season 4_2026.xlsx" data/raw/cardiac_dataset.xlsx
```

The loader also accepts the original filename unchanged, or any single `.xlsx`
in `data/raw/`. To point elsewhere, set `CARDIAC_DATA_FILE` in `.env`.

### Build and verify

```bash
cardiac-agent build
cardiac-agent doctor
```

`doctor` checks the config file, the workbook, the warehouse, the signal
corpus, the model credentials and the framework weights, and exits non-zero if
anything is wrong. A healthy build reports roughly:

```
sku rows: 7452
space rows: 326
market value latest cr: 23244.48
focal value latest cr: 389.49
focal share pct: 1.6756
```

### First question

```bash
cardiac-agent ask "Which two or three opportunity spaces should Cipla prioritise?"
```

---

## Optional: enable the language model

The deterministic path is complete without this. A model adds fluency and the
ability to answer question shapes the planner did not anticipate.

```bash
cp .env.example .env
```

Then set:

```bash
CARDIAC_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
CARDIAC_LLM_MODEL=claude-opus-5
CARDIAC_LLM_EFFORT=high
```

Verify with `cardiac-agent doctor`; the Model section should report
`credentials: found`.

To force deterministic mode explicitly, set `CARDIAC_LLM_PROVIDER=none`. That is
the right setting for the evaluation suite, because it is reproducible.

---

## Development install

```bash
pip install -r requirements-dev.txt
pytest                    # 150 tests
ruff check src tests
python evaluation/run_eval.py
```

Tests that need the warehouse are marked `requires_data` and skip cleanly when
it has not been built, so the suite runs on a fresh clone.

---

## Docker

```bash
docker compose up --build
```

Brings up the API on `http://localhost:8000` and the Streamlit console on
`http://localhost:8501`. `data/` is bind-mounted, so place the workbook in
`data/raw/` before starting and the warehouse persists across restarts.

To build the warehouse inside the container:

```bash
docker compose run --rm api cardiac-agent build
```

---

## Troubleshooting

**`Could not find the Cardiac workbook`**
The file is not in `data/raw/` under a recognised name. Copy it to
`data/raw/cardiac_dataset.xlsx` or set `CARDIAC_DATA_FILE` to an absolute path.

**`The Cardiac sheet is missing required columns: ...`**
The workbook does not match the expected schema. If the organisers reissued the
file with different period labels, update `REQUIRED_COLUMNS` in
`src/cardiac_agent/ingestion/excel_loader.py` and the `market.periods` block in
`config/settings.yaml` together.

**`No warehouse at ...`**
Run `cardiac-agent build`.

**`Warehouse at ... is incomplete`**
A build was interrupted. Run `cardiac-agent build --force`.

**`No opportunity spaces survived the filters`**
Either the warehouse is empty or `market.min_space_value_cr` is set too high
for the data. Check `cardiac-agent doctor` first.

**Right-to-win scores are all zero**
`market.focal_company` does not match any value in the COMPANY column. The
audit marks consolidated groups with a trailing asterisk, so the value is
`CIPLA*` rather than `CIPLA`. The ingestion log emits
`normalize.focal_company_absent` when this happens.

**`ModuleNotFoundError: cardiac_agent`**
The package is not installed. Run `pip install -e .` from the project root, or
prefix commands with `PYTHONPATH=src`.

**Streamlit cannot import `cardiac_agent`**
Run it from the project root:
`streamlit run src/cardiac_agent/ui/streamlit_app.py`. The app adds `src/` to
`sys.path` itself, so an editable install is not strictly required.

**The agent answers but says "deterministic renderer"**
No model credentials were found, or the provider call failed. This is a
supported mode, not an error. Check `cardiac-agent doctor` if you expected a
model to be used; the run trace records the reason under `warnings`.

**Sensitivity analysis feels slow**
It runs 500 re-scorings and takes about four seconds at molecule level. Reduce
`sensitivity.iterations` in `config/settings.yaml` if you need it faster; below
about 200 the frequencies get noisy.

**Windows console shows garbled characters**
The output includes the rupee sign. Use Windows Terminal, or run
`chcp 65001` before the command.
