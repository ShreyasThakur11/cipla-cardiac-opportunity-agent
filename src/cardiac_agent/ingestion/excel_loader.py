"""Read the Cardiac workbook and fail loudly when it is not what we expect.

The organisers supply one file with two sheets: ``Glossary`` (metric
definitions) and ``Cardiac`` (one row per pack, roughly 7.5k rows, 36 columns).
Everything downstream assumes that shape, so the schema is asserted here rather
than discovered halfway through a scoring run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)

CARDIAC_SHEET = "Cardiac"
GLOSSARY_SHEET = "Glossary"

#: Columns that must exist for the pipeline to mean anything. The workbook has
#: more; these are the ones the analysis actually reads.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "KEY(MS+SG+FINAL NFC)",
    "Plain/Combination",
    "MOLECULE_DESC",
    "STRENGTH (ONLY 1 MOL.)",
    "PACK_DESC",
    "BRANDS",
    "COMPANY",
    "INDIAN_MNC",
    "SUBGROUP",
    "GROUP",
    "SUPERGROUP",
    "ACUTE_CHRONIC",
    "FINAL NFC",
    "CARDIAC SEGMENT",
    "CARDIAC SUB SEGMENTS",
    "MAT FEB'24",
    "MAT FEB'25",
    "MAT FEB'26",
    "Sales 'DEC'25",
    "Sales 'JAN'26",
    "Sales 'FEB'26",
    "MAT CP FEB'24",
    "MAT CP FEB'25",
    "MAT CP FEB'26",
    "QTY MAT FEB'24",
    "QTY MAT FEB'25",
    "QTY MAT FEB'26",
    "PR_DEC'25",
    "PR_JAN'26",
    "PR_FEB'26",
)

#: Columns that must be numeric. Anything unparseable becomes 0.0 with a warning
#: rather than silently propagating NaN into a market-size total.
NUMERIC_COLUMNS: tuple[str, ...] = tuple(
    column for column in REQUIRED_COLUMNS if column.startswith(("MAT", "Sales", "QTY", "PR_"))
)


class WorkbookSchemaError(ValueError):
    """The supplied workbook does not match the expected Cardiac schema."""


def load_cardiac_workbook(path: Path | None = None) -> pd.DataFrame:
    """Load and validate the ``Cardiac`` sheet.

    Args:
        path: Explicit workbook location. Defaults to the configured file.

    Returns:
        One row per pack, with numeric columns coerced to float.

    Raises:
        WorkbookSchemaError: A required column or the sheet itself is missing.
    """
    resolved = path or get_settings().resolve_data_file()
    logger.info("workbook.load.start", path=str(resolved))

    try:
        frame = pd.read_excel(resolved, sheet_name=CARDIAC_SHEET, engine="openpyxl")
    except ValueError as exc:  # pandas raises ValueError for a missing sheet
        raise WorkbookSchemaError(
            f"Worksheet '{CARDIAC_SHEET}' not found in {resolved}. "
            "Confirm you are pointing at the Ascend Cardiac dataset."
        ) from exc

    frame.columns = [str(column).strip() for column in frame.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise WorkbookSchemaError(
            "The Cardiac sheet is missing required columns: "
            + ", ".join(missing)
            + ". The pipeline is built against the Ascend Season 4 schema; if the "
            "organisers have reissued the file, update REQUIRED_COLUMNS and the "
            "period map in config/settings.yaml together."
        )

    if frame.empty:
        raise WorkbookSchemaError(f"The Cardiac sheet in {resolved} has no data rows.")

    for column in NUMERIC_COLUMNS:
        coerced = pd.to_numeric(frame[column], errors="coerce")
        unparseable = int(coerced.isna().sum() - frame[column].isna().sum())
        if unparseable > 0:
            logger.warning(
                "workbook.numeric.coerced",
                column=column,
                unparseable_rows=unparseable,
            )
        frame[column] = coerced.fillna(0.0).astype(float)

    # Text columns: strip whitespace once, here, so no downstream join has to
    # worry about " CIPLA*" not matching "CIPLA*".
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].astype(str).str.strip()

    logger.info(
        "workbook.load.done",
        rows=len(frame),
        columns=len(frame.columns),
        total_mat_latest=float(frame["MAT FEB'26"].sum()),
    )
    return frame


def load_glossary(path: Path | None = None) -> pd.DataFrame:
    """Load the ``Glossary`` sheet as term/definition pairs.

    The glossary is small but load-bearing: it is what tells us MAT CP removes
    price effects and QTY reflects consumption. It is indexed into the retrieval
    corpus so the agent can quote the organisers' own definitions when it
    explains a metric.
    """
    resolved = path or get_settings().resolve_data_file()
    try:
        raw = pd.read_excel(resolved, sheet_name=GLOSSARY_SHEET, engine="openpyxl", header=None)
    except ValueError:
        logger.warning("glossary.missing", path=str(resolved))
        return pd.DataFrame(columns=["term", "full_form", "definition"])

    records: list[dict[str, str]] = []
    for _, row in raw.iterrows():
        values = [("" if pd.isna(cell) else str(cell).strip()) for cell in row.tolist()]
        values += [""] * (3 - len(values))
        term, full_form, definition = values[0], values[1], values[2]
        if not term or term.lower() == "terms":
            # Trailing narrative lines in the sheet have no term in column A but
            # do carry guidance ("MAT CP should be used to understand real
            # demand growth"). Keep them as definitions with a synthetic term.
            if full_form or definition:
                records.append({"term": "Guidance", "full_form": "", "definition": full_form or definition})
            continue
        records.append({"term": term, "full_form": full_form, "definition": definition})

    glossary = pd.DataFrame(records, columns=["term", "full_form", "definition"])
    logger.info("glossary.load.done", entries=len(glossary))
    return glossary


__all__ = [
    "CARDIAC_SHEET",
    "GLOSSARY_SHEET",
    "NUMERIC_COLUMNS",
    "REQUIRED_COLUMNS",
    "WorkbookSchemaError",
    "load_cardiac_workbook",
    "load_glossary",
]
