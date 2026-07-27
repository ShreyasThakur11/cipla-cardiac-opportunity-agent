"""Assemble the DuckDB warehouse the rest of the system reads from.

Why DuckDB rather than pandas alone: the agent is allowed to run ad-hoc SQL
when a question does not fit a pre-built tool. Handing a model a real query
engine with a read-only connection is safer and far more expressive than
letting it construct pandas expressions, and DuckDB needs no server, no
credentials and no container - it is one file next to the code.

Tables written:

``sku_facts``          one row per pack, with derived columns
``space_facts``        one row per opportunity space, with summed measures
``space_membership``   SKU-to-space map, so any subset can be recomputed
``company_facts``      one row per company per space, for competitive structure
``brand_facts``        one row per brand per space
``glossary``           the organisers' own metric definitions
``build_metadata``     what was built, from which file, under which config
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ..config import get_framework, get_settings
from ..logging_config import get_logger
from .excel_loader import load_cardiac_workbook, load_glossary
from .normalize import normalize_cardiac_frame
from .spaces import build_all_spaces

logger = get_logger(__name__)


def _file_digest(path: Path) -> str:
    """SHA-256 of the source workbook, recorded so a run can be tied to inputs."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _company_facts(
    frame: pd.DataFrame, membership: pd.DataFrame, periods: dict
) -> pd.DataFrame:
    """Value by company within every space - the input to concentration metrics."""
    value = periods["value"]
    facts = frame.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[["row_id", "company_clean", "COMPANY", "is_mnc", value["t1"], value["t2"]]],
        on="row_id",
        how="left",
        validate="many_to_one",
    ).rename(columns={value["t1"]: "value_t1", value["t2"]: "value_t2"})

    grouped = joined.groupby(
        ["level", "space_id", "space_label", "company_clean", "COMPANY"], as_index=False
    ).agg(value_t1=("value_t1", "sum"), value_t2=("value_t2", "sum"), is_mnc=("is_mnc", "max"))

    totals = grouped.groupby(["level", "space_id"], as_index=False)["value_t2"].sum().rename(
        columns={"value_t2": "space_value_t2"}
    )
    grouped = grouped.merge(totals, on=["level", "space_id"], how="left")
    grouped["share_t2"] = (
        grouped["value_t2"].divide(grouped["space_value_t2"].where(grouped["space_value_t2"] != 0))
        .fillna(0.0)
    )
    grouped["rank_in_space"] = grouped.groupby(["level", "space_id"])["value_t2"].rank(
        ascending=False, method="min"
    ).astype(int)
    return grouped


def _brand_facts(
    frame: pd.DataFrame, membership: pd.DataFrame, periods: dict
) -> pd.DataFrame:
    """Value by brand within every space - used for competitor and franchise views."""
    value = periods["value"]
    facts = frame.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[["row_id", "BRANDS", "brand_root", "company_clean", value["t1"], value["t2"]]],
        on="row_id",
        how="left",
        validate="many_to_one",
    ).rename(columns={value["t1"]: "value_t1", value["t2"]: "value_t2"})

    grouped = joined.groupby(
        ["level", "space_id", "space_label", "BRANDS", "brand_root", "company_clean"],
        as_index=False,
    ).agg(value_t1=("value_t1", "sum"), value_t2=("value_t2", "sum"))
    grouped = grouped.rename(columns={"BRANDS": "brand"})
    grouped["rank_in_space"] = grouped.groupby(["level", "space_id"])["value_t2"].rank(
        ascending=False, method="min"
    ).astype(int)
    return grouped


def build_warehouse(
    workbook: Path | None = None, warehouse: Path | None = None
) -> dict[str, Any]:
    """Run the full ingestion pipeline and persist the warehouse.

    Args:
        workbook: Source Excel file. Defaults to the configured location.
        warehouse: Destination DuckDB file. Defaults to the configured path.

    Returns:
        Build metadata: row counts, market totals and the source digest.
    """
    settings = get_settings()
    framework = get_framework()
    settings.ensure_directories()

    source = workbook or settings.resolve_data_file()
    destination = warehouse or settings.warehouse_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    periods = framework.require("market.periods")
    focal_company = framework.get_path("market.focal_company", "CIPLA*")

    raw = load_cardiac_workbook(source)
    frame = normalize_cardiac_frame(raw, focal_company=focal_company)
    glossary = load_glossary(source)
    spaces, membership = build_all_spaces(frame, periods)
    companies = _company_facts(frame, membership, periods)
    brands = _brand_facts(frame, membership, periods)

    # Lists are not a DuckDB-friendly column type coming from pandas objects;
    # store the joined string form and keep the list only in memory.
    persistable = frame.drop(columns=["molecules"])

    market_total = float(frame[periods["value"]["t2"]].sum())
    focal_total = float(frame.loc[frame["is_focal"], periods["value"]["t2"]].sum())

    metadata = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file": str(source),
        "source_sha256": _file_digest(source),
        "config_file": str(settings.config_file),
        "sku_rows": int(len(frame)),
        "space_rows": int(len(spaces)),
        "membership_rows": int(len(membership)),
        "market_value_latest_cr": round(market_total, 2),
        "focal_value_latest_cr": round(focal_total, 2),
        "focal_share_pct": round(100.0 * focal_total / market_total, 4) if market_total else 0.0,
        "currency_unit": framework.get_path("market.currency_unit", "INR crore"),
        "as_of": framework.get_path("market.as_of", ""),
    }

    connection = duckdb.connect(str(destination))
    try:
        connection.execute("BEGIN TRANSACTION")
        for name, payload in (
            ("sku_facts", persistable),
            ("space_facts", spaces),
            ("space_membership", membership),
            ("company_facts", companies),
            ("brand_facts", brands),
            ("glossary", glossary),
        ):
            connection.register("_incoming", payload)
            connection.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _incoming")
            connection.unregister("_incoming")

        meta_frame = pd.DataFrame([{"key": k, "value": json.dumps(v)} for k, v in metadata.items()])
        connection.register("_incoming", meta_frame)
        connection.execute("CREATE OR REPLACE TABLE build_metadata AS SELECT * FROM _incoming")
        connection.unregister("_incoming")
        connection.execute("COMMIT")
    finally:
        connection.close()

    # A parquet mirror makes the warehouse readable by anything - Excel via
    # Power Query, R, a notebook - without a DuckDB dependency.
    parquet_dir = destination.parent / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)
    persistable.to_parquet(parquet_dir / "sku_facts.parquet", index=False)
    spaces.to_parquet(parquet_dir / "space_facts.parquet", index=False)
    companies.to_parquet(parquet_dir / "company_facts.parquet", index=False)

    (destination.parent / "build_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    logger.info("warehouse.built", destination=str(destination), **{
        k: v for k, v in metadata.items() if k not in {"source_sha256", "config_file"}
    })
    return metadata


__all__ = ["build_warehouse"]
