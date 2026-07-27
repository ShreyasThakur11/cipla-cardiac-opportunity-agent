"""Shared fixtures.

Two kinds of test live here. Most run against a small synthetic market built in
memory: fast, hermetic, and they exercise the maths without needing the
competition dataset, which is not in the repository. A smaller set is marked
``requires_data`` and runs against the real warehouse when it has been built.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cardiac_agent.config import get_framework, get_settings  # noqa: E402


@pytest.fixture(scope="session")
def framework():
    return get_framework()


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def warehouse_available(settings) -> bool:
    return settings.warehouse_path.exists()


@pytest.fixture(scope="session")
def real_context(warehouse_available):
    """The real analysis context, skipping the test when it is not built."""
    if not warehouse_available:
        pytest.skip("Warehouse not built; run `cardiac-agent build` first.")
    from cardiac_agent.pipeline import get_context

    return get_context()


@pytest.fixture
def synthetic_skus() -> pd.DataFrame:
    """A tiny, hand-checkable market.

    Four molecules across two segments, with values chosen so the expected
    metrics can be computed by hand in the test rather than by re-running the
    code under test.
    """
    rows = [
        # label, company, molecule, segment, sub-segment, group, subgroup,
        # v24, v25, v26, cp24, cp25, cp26, q24, q25, q26
        (
            "BRAND-A",
            "CIPLA*",
            "TELMISARTAN",
            "Anti Hypertensives",
            "ARBs",
            "C02C ARB",
            "C02C04 TELMISARTAN",
            80.0,
            90.0,
            100.0,
            80.0,
            88.0,
            96.0,
            800.0,
            880.0,
            950.0,
        ),
        (
            "BRAND-B",
            "TORRENT*",
            "TELMISARTAN",
            "Anti Hypertensives",
            "ARBs",
            "C02C ARB",
            "C02C04 TELMISARTAN",
            200.0,
            240.0,
            300.0,
            200.0,
            235.0,
            280.0,
            2000.0,
            2300.0,
            2700.0,
        ),
        (
            "BRAND-C",
            "SUN*",
            "AMLODIPINE + TELMISARTAN",
            "Anti Hypertensives",
            "AHT Dual Comb.",
            "C02F DUAL",
            "C02F06 AMLODIPINE+TELMISARTAN",
            150.0,
            190.0,
            250.0,
            150.0,
            185.0,
            240.0,
            1500.0,
            1850.0,
            2350.0,
        ),
        (
            "BRAND-D",
            "CIPLA*",
            "ROSUVASTATIN",
            "Lipid Regulators",
            "Statins Plain",
            "C10A STATINS",
            "C10A04 ROSUVASTATIN",
            100.0,
            105.0,
            108.0,
            100.0,
            102.0,
            101.0,
            1000.0,
            1010.0,
            1000.0,
        ),
        (
            "BRAND-E",
            "LUPIN*",
            "ROSUVASTATIN",
            "Lipid Regulators",
            "Statins Plain",
            "C10A STATINS",
            "C10A04 ROSUVASTATIN",
            300.0,
            330.0,
            360.0,
            300.0,
            325.0,
            350.0,
            3000.0,
            3250.0,
            3500.0,
        ),
        (
            "BRAND-F",
            "ZYDUS*",
            "EZETIMIBE + ROSUVASTATIN",
            "Lipid Regulators",
            "Statins Comb.",
            "C10A STATINS",
            "C10A0S ROSUVASTATIN + EZETIMIBE",
            10.0,
            40.0,
            120.0,
            10.0,
            38.0,
            112.0,
            100.0,
            400.0,
            1150.0,
        ),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "BRANDS",
            "COMPANY",
            "MOLECULE_DESC",
            "CARDIAC SEGMENT",
            "CARDIAC SUB SEGMENTS",
            "GROUP",
            "SUBGROUP",
            "MAT FEB'24",
            "MAT FEB'25",
            "MAT FEB'26",
            "MAT CP FEB'24",
            "MAT CP FEB'25",
            "MAT CP FEB'26",
            "QTY MAT FEB'24",
            "QTY MAT FEB'25",
            "QTY MAT FEB'26",
        ],
    )
    frame["KEY(MS+SG+FINAL NFC)"] = frame["SUBGROUP"] + "SOLIDS"
    frame["Plain/Combination"] = (
        frame["MOLECULE_DESC"].str.contains(r"\+").map({True: "Combination", False: "Plain"})
    )
    frame["STRENGTH (ONLY 1 MOL.)"] = "10 MG"
    frame["PACK VOLUME"] = "0"
    frame["PACK_DESC"] = frame["BRANDS"] + " TAB 10 MG x 10"
    frame["MANUFACT. DESC"] = frame["COMPANY"]
    frame["INDIAN_MNC"] = "INDIAN"
    frame["SUPERGROUP"] = "CARDIAC"
    frame["ACUTE_CHRONIC"] = "CHRONIC"
    frame["FINAL NFC"] = "SOLIDS"
    for column in ("Sales 'DEC'25", "Sales 'JAN'26", "Sales 'FEB'26"):
        frame[column] = frame["MAT FEB'26"] / 12.0
    for column in ("PR_DEC'25", "PR_JAN'26", "PR_FEB'26"):
        frame[column] = 10.0
    return frame


@pytest.fixture
def synthetic_context(synthetic_skus, framework):
    """A minimal end-to-end analysis built from the synthetic market."""
    from cardiac_agent.analytics.competition import add_competition_metrics
    from cardiac_agent.analytics.metrics import add_growth_metrics
    from cardiac_agent.analytics.rightowin import add_right_to_win_metrics
    from cardiac_agent.ingestion.normalize import normalize_cardiac_frame
    from cardiac_agent.ingestion.spaces import build_all_spaces

    normalised = normalize_cardiac_frame(synthetic_skus, focal_company="CIPLA*")
    spaces, membership = build_all_spaces(normalised, framework.require("market.periods"))

    facts = normalised.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[["row_id", "company_clean", "COMPANY", "is_mnc", "MAT FEB'25", "MAT FEB'26"]],
        on="row_id",
        how="left",
    ).rename(columns={"MAT FEB'25": "value_t1", "MAT FEB'26": "value_t2"})
    company_facts = joined.groupby(
        ["level", "space_id", "space_label", "company_clean", "COMPANY"], as_index=False
    ).agg(value_t1=("value_t1", "sum"), value_t2=("value_t2", "sum"), is_mnc=("is_mnc", "max"))
    totals = (
        company_facts.groupby(["level", "space_id"], as_index=False)["value_t2"]
        .sum()
        .rename(columns={"value_t2": "space_value_t2"})
    )
    company_facts = company_facts.merge(totals, on=["level", "space_id"], how="left")
    company_facts["share_t2"] = company_facts["value_t2"] / company_facts["space_value_t2"]
    company_facts["rank_in_space"] = (
        company_facts.groupby(["level", "space_id"])["value_t2"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    enriched = add_growth_metrics(spaces)
    enriched = add_competition_metrics(enriched, company_facts)
    enriched = add_right_to_win_metrics(enriched, normalised, membership)
    enriched["trend_multiplier"] = 1.0
    return {
        "skus": normalised,
        "spaces": spaces,
        "membership": membership,
        "company_facts": company_facts,
        "enriched": enriched,
    }
