# Raw inputs (not committed)

This directory holds the competition inputs. They are **deliberately excluded
from version control**, because they are licensed material supplied by the
organisers and redistributing them would breach the terms of the case.

## What to put here

| File | Where it comes from |
| --- | --- |
| `cardiac_dataset.xlsx` | `Data Set_Ascend Season 4_2026.xlsx`, renamed |
| `case_study.pdf` *(optional)* | `Case Study_Ascend Season 4_2026.pdf` |

The loader also accepts the original filename unchanged, or any single `.xlsx`
dropped into this folder. To point somewhere else entirely, set
`CARDIAC_DATA_FILE` in your `.env`.

## Expected shape

The `Cardiac` worksheet must carry 36 columns including `MAT FEB'24/25/26`,
`MAT CP FEB'24/25/26`, `QTY MAT FEB'24/25/26`, the three monthly `Sales`
columns and the three `PR_` price-to-retailer columns. A `Glossary` worksheet
supplies the metric definitions.

Ingestion validates this on load and fails with a named list of missing columns
rather than producing a silently wrong answer. If the organisers reissue the
file with different period labels, update `REQUIRED_COLUMNS` in
`src/cardiac_agent/ingestion/excel_loader.py` and the `market.periods` block in
`config/settings.yaml` together.

## Then

```bash
cardiac-agent build
```

The build records a SHA-256 of the source file in `build_metadata`, so any
result can be tied back to the exact input it came from.
