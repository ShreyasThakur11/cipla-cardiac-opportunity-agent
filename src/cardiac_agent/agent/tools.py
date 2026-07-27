"""The agent's tool surface.

Every tool is a thin wrapper over the deterministic analytics package. None of
them takes a free-text instruction that could change a calculation, and none
returns prose. They return structured evidence, which the model then narrates.

That constraint is what makes the numeric guardrail work: the union of every
tool result is the complete set of figures the agent is permitted to state. A
number in the answer that is not in the evidence pack was invented, and the
verifier rejects the answer.

Tool design follows the same rules used for any well-behaved agent: names that
say what they do, descriptions that say *when* to call them, and schemas tight
enough that a wrong argument is a validation error rather than a wrong answer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import duckdb
import pandas as pd

from ..analytics.competition import top_competitors
from ..analytics.forecast import forecast_space as run_forecast
from ..analytics.scoring import explain_score
from ..analytics.sensitivity import run_sensitivity
from ..analytics.whitespace import find_whitespace
from ..logging_config import get_logger
from ..pipeline import AnalysisContext

logger = get_logger(__name__)

SPACE_LEVELS_ENUM = [
    "segment",
    "sub_segment",
    "molecule_class",
    "molecule_combination",
    "treatment_archetype",
    "anchor_molecule",
]

#: Columns returned by the ranking tool, in the order a reader wants them.
RANKING_COLUMNS = [
    "space_id",
    "space_label",
    "value_t2",
    "value_yoy",
    "value_cagr_2y",
    "real_growth",
    "volume_growth",
    "price_effect",
    "momentum",
    "hhi",
    "n_players",
    "leader_company",
    "leader_share",
    "focal_share_t2",
    "focal_growth_gap",
    "trend_multiplier",
    "market_opportunity_index",
    "right_to_win_score",
    "cipla_priority_score",
    "moi_rank",
    "cps_rank",
    "strategic_verdict",
]


class ToolError(RuntimeError):
    """A tool was called with arguments it cannot satisfy."""


@dataclass
class ToolSpec:
    """A tool definition plus its implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _round_frame(frame: pd.DataFrame, decimals: int = 4) -> list[dict[str, Any]]:
    """Frame to JSON-safe records, with floats rounded for readability."""
    if frame.empty:
        return []
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].round(decimals)
        elif pd.api.types.is_bool_dtype(out[column]):
            out[column] = out[column].astype(bool)
    return out.where(pd.notna(out), None).to_dict(orient="records")


def _percentify(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Express rate columns as percentages.

    The model reads these directly into prose, and a value of 0.1985 invites a
    transcription error that "19.85%" does not.
    """
    rate_columns = {
        "value_yoy",
        "value_cagr_2y",
        "real_growth",
        "volume_growth",
        "price_effect",
        "momentum",
        "leader_share",
        "focal_share_t2",
        "focal_growth_gap",
        "top3_share",
        # Competitor tables use their own column names for the same quantities.
        "share_t2",
        "yoy",
        "penetration_index",
    }
    for record in records:
        for column in list(record):
            if column in rate_columns and isinstance(record[column], (int, float)):
                record[f"{column}_pct"] = round(record[column] * 100.0, 2)
                del record[column]
    return records


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def market_overview(context: AnalysisContext) -> dict[str, Any]:
    """Therapy-area totals and the focal company's standing."""
    totals = context.totals
    segments = context.enriched[context.enriched["level"] == "segment"].sort_values(
        "value_t2", ascending=False
    )
    return {
        "as_of": context.as_of,
        "currency_unit": context.currency_unit,
        "market_value_cr": round(totals["market_value_t2"], 1),
        "market_value_prior_cr": round(totals["market_value_t1"], 1),
        "market_growth_pct": round(totals["market_yoy"] * 100.0, 2),
        "market_cagr_2y_pct": round(totals["market_cagr_2y"] * 100.0, 2),
        "market_real_growth_pct": round(totals["market_real_growth"] * 100.0, 2),
        "market_volume_growth_pct": round(totals["market_volume_growth"] * 100.0, 2),
        "market_price_effect_pct": round(totals["market_price_effect"] * 100.0, 2),
        "focal_company": context.focal_label,
        "focal_value_cr": round(totals["focal_value_t2"], 1),
        "focal_share_pct": round(totals["focal_share"] * 100.0, 2),
        "focal_growth_pct": round(totals["focal_yoy"] * 100.0, 2),
        "focal_growth_gap_pp": round((totals["focal_yoy"] - totals["market_yoy"]) * 100.0, 2),
        "sku_rows": int(context.metadata.get("sku_rows", 0)),
        "spaces_scored": int(len(context.scored)),
        "segments": _percentify(
            _round_frame(
                segments[
                    [
                        "space_label",
                        "value_t2",
                        "value_yoy",
                        "real_growth",
                        "volume_growth",
                        "hhi",
                        "n_players",
                        "focal_share_t2",
                    ]
                ]
            )
        ),
        "interpretation_note": (
            "MAT is reported value and moves on both price and demand. MAT CP holds "
            "prices at the prior year to isolate demand, and QTY MAT confirms it. The "
            "gap between reported and real growth is the price contribution."
        ),
    }


def rank_opportunity_spaces(
    context: AnalysisContext,
    level: str = "molecule_combination",
    top_n: int = 10,
    rank_by: str = "cipla_priority_score",
    min_value_cr: float | None = None,
) -> dict[str, Any]:
    """Rank spaces at one level by opportunity or by Cipla priority."""
    if level not in SPACE_LEVELS_ENUM:
        raise ToolError(f"Unknown level '{level}'. Choose one of {SPACE_LEVELS_ENUM}.")
    if rank_by not in {"cipla_priority_score", "market_opportunity_index", "value_t2", "value_yoy"}:
        raise ToolError(
            "rank_by must be cipla_priority_score, market_opportunity_index, value_t2 or value_yoy."
        )

    frame = context.scored[context.scored["level"] == level]
    if min_value_cr is not None:
        frame = frame[frame["value_t2"] >= float(min_value_cr)]
    if frame.empty:
        raise ToolError(f"No spaces at level '{level}' cleared the filters.")

    ordered = frame.sort_values(rank_by, ascending=False).head(int(top_n))
    columns = [column for column in RANKING_COLUMNS if column in ordered.columns]
    return {
        "level": level,
        "level_description": str(ordered["level_description"].iloc[0]),
        "ranked_by": rank_by,
        "count": int(len(ordered)),
        "currency_unit": context.currency_unit,
        "spaces": _percentify(_round_frame(ordered[columns])),
        "scoring_note": (
            "Market Opportunity Index ignores Cipla entirely. Cipla Priority Score is "
            "that index multiplied by a right-to-win gate. A space with a high index "
            "and a low priority score is one somebody else is positioned to win."
        ),
    }


def space_deep_dive(
    context: AnalysisContext, space: str, level: str | None = None
) -> dict[str, Any]:
    """Full evidence card for one space: metrics, competitors, signals, score."""
    row = context.find_space(space, level)
    if row is None:
        raise ToolError(
            f"No space matches '{space}'"
            + (f" at level '{level}'" if level else "")
            + ". Call rank_opportunity_spaces first to see the available labels."
        )

    competitors = top_competitors(context.company_facts, row["level"], row["space_id"], limit=8)
    space_brands = context.brand_facts[
        (context.brand_facts["level"] == row["level"])
        & (context.brand_facts["space_id"] == row["space_id"])
    ].sort_values("value_t2", ascending=False)
    brands = space_brands.head(6)

    # Search the full brand list, not the top six. Cipla is outside the top six
    # in most spaces, and reporting "no brands here" where it holds a real
    # position would understate its right to win.
    focal_brands = space_brands[
        (space_brands["company_clean"].str.upper() == context.focal_label.upper())
        & (space_brands["value_t2"] > 0)
    ].head(6)

    signals = context.space_signals(row["space_id"])

    return {
        "space_id": row["space_id"],
        "space_label": row["space_label"],
        "level": row["level"],
        "segment": row.get("segment", ""),
        "sub_segment": row.get("sub_segment", ""),
        "currency_unit": context.currency_unit,
        "size_and_growth": {
            "value_cr": round(float(row["value_t2"]), 1),
            "value_prior_cr": round(float(row["value_t1"]), 1),
            "absolute_growth_cr": round(float(row["absolute_growth_cr"]), 1),
            "value_growth_pct": round(float(row["value_yoy"]) * 100.0, 2),
            "value_cagr_2y_pct": round(float(row["value_cagr_2y"]) * 100.0, 2),
            "real_growth_pct": round(float(row["real_growth"]) * 100.0, 2),
            "volume_growth_pct": round(float(row["volume_growth"]) * 100.0, 2),
            "price_effect_pct": round(float(row["price_effect"]) * 100.0, 2),
            "momentum_pct": round(float(row["momentum"]) * 100.0, 2),
            "share_of_cardiac_pct": round(float(row["share_of_cardiac_pct"]), 2),
        },
        "competition": {
            "hhi": round(float(row["hhi"]), 0),
            "concentration": row["concentration_label"],
            "players": int(row["n_players"]),
            "leader": row["leader_company"],
            "leader_share_pct": round(float(row["leader_share"]) * 100.0, 2),
            "top3_share_pct": round(float(row["top3_share"]) * 100.0, 2),
            "share_churn_pct": round(float(row["share_churn"]) * 100.0, 2),
            "new_entrants": int(row["new_entrant_count"]),
            "crowding_players_per_100cr": round(float(row["crowding"]), 2),
            "top_companies": _percentify(_round_frame(competitors)),
            "top_brands": _round_frame(
                brands[["brand", "company_clean", "value_t2", "value_t1"]]
            ),
        },
        "cipla_position": {
            "value_cr": round(float(row["focal_value_t2"]), 2),
            "share_pct": round(float(row["focal_share_t2"]) * 100.0, 2),
            "share_change_pp": round(float(row["focal_share_delta_pp"]), 2),
            "growth_pct": round(float(row["focal_yoy"]) * 100.0, 2),
            "growth_vs_market_pp": round(float(row["focal_growth_gap"]) * 100.0, 2),
            "present": bool(row["focal_present"]),
            "brands_here": _round_frame(focal_brands[["brand", "value_t2"]]),
            "adjacent_brands": row.get("adjacent_cipla_brands", ""),
            "molecule_adjacency_pct": round(float(row["rtw_molecule_adjacency"]) * 100.0, 1),
            "brand_franchise_score": round(float(row["rtw_brand_franchise"]), 2),
            "detailing_adjacency_pct": round(float(row["rtw_detailing_adjacency"]) * 100.0, 2),
        },
        "external_signals": {
            "trend_multiplier": round(float(row["trend_multiplier"]), 3),
            "signal_ids": str(row.get("trend_signal_ids", "")).split(",") if row.get("trend_signal_ids") else [],
            "links": signals,
        },
        "scores": explain_score(row),
    }


def compare_spaces(
    context: AnalysisContext, spaces: list[str], level: str | None = None
) -> dict[str, Any]:
    """Side-by-side comparison, built to expose trade-offs rather than hide them."""
    if not spaces:
        raise ToolError("Provide at least two space identifiers or labels to compare.")
    rows: list[pd.Series] = []
    missing: list[str] = []
    for identifier in spaces:
        row = context.find_space(identifier, level)
        if row is None:
            missing.append(identifier)
        else:
            rows.append(row)
    if not rows:
        raise ToolError(f"None of {spaces} matched a scored space.")

    frame = pd.DataFrame(rows)
    columns = [column for column in RANKING_COLUMNS if column in frame.columns]
    comparison = _percentify(_round_frame(frame[columns]))

    # Name the tensions explicitly. This is the part the case marks on.
    tradeoffs: list[str] = []
    if len(frame) >= 2:
        largest = frame.loc[frame["value_t2"].idxmax()]
        fastest = frame.loc[frame["real_growth"].idxmax()]
        if largest["space_id"] != fastest["space_id"]:
            tradeoffs.append(
                f"Size versus growth: {largest['space_label']} is the largest at "
                f"{largest['value_t2']:.0f} crore, but {fastest['space_label']} is growing "
                f"faster in real terms ({fastest['real_growth'] * 100:.1f}% against "
                f"{largest['real_growth'] * 100:.1f}%)."
            )
        most_open = frame.loc[frame["hhi"].idxmin()]
        if most_open["space_id"] != fastest["space_id"]:
            tradeoffs.append(
                f"Growth versus competition: {most_open['space_label']} is the most open "
                f"(HHI {most_open['hhi']:.0f}) while the fastest grower "
                f"{fastest['space_label']} sits at HHI {fastest['hhi']:.0f}."
            )
        best_moi = frame.loc[frame["market_opportunity_index"].idxmax()]
        best_cps = frame.loc[frame["cipla_priority_score"].idxmax()]
        if best_moi["space_id"] != best_cps["space_id"]:
            tradeoffs.append(
                f"Attractiveness versus right to win: {best_moi['space_label']} scores highest "
                f"on market opportunity ({best_moi['market_opportunity_index']:.1f}) but "
                f"{best_cps['space_label']} wins on Cipla priority "
                f"({best_cps['cipla_priority_score']:.1f}) because its right-to-win score is "
                f"{best_cps['right_to_win_score']:.1f} against "
                f"{best_moi['right_to_win_score']:.1f}."
            )

    return {
        "comparison": comparison,
        "trade_offs": tradeoffs,
        "not_found": missing,
        "currency_unit": context.currency_unit,
    }


def competitor_profile(context: AnalysisContext, company: str) -> dict[str, Any]:
    """Where one competitor is strong, and where it overlaps with Cipla."""
    facts = context.company_facts
    needle = company.strip().upper()
    matches = facts[facts["company_clean"].str.upper().str.contains(needle, regex=False)]
    if matches.empty:
        available = sorted(
            facts.groupby("company_clean")["value_t2"].sum().nlargest(15).index.tolist()
        )
        raise ToolError(f"No company matches '{company}'. Largest players include: {available}.")

    resolved = matches.groupby("company_clean")["value_t2"].sum().idxmax()
    company_rows = facts[facts["company_clean"] == resolved]

    segment_rows = company_rows[company_rows["level"] == "segment"]
    total_value = float(segment_rows["value_t2"].sum())
    total_prior = float(segment_rows["value_t1"].sum())

    strongholds = (
        company_rows[company_rows["level"] == "sub_segment"]
        .sort_values("value_t2", ascending=False)
        .head(8)[["space_label", "value_t2", "share_t2", "rank_in_space"]]
    )

    brands = (
        context.brand_facts[
            (context.brand_facts["company_clean"] == resolved)
            & (context.brand_facts["level"] == "segment")
        ]
        .sort_values("value_t2", ascending=False)
        .head(8)[["brand", "value_t2", "value_t1"]]
    )

    return {
        "company": resolved,
        "currency_unit": context.currency_unit,
        "cardiac_value_cr": round(total_value, 1),
        "cardiac_share_pct": round(
            100.0 * total_value / context.totals["market_value_t2"], 2
        ),
        "growth_pct": round(
            (total_value / total_prior - 1.0) * 100.0 if total_prior else 0.0, 2
        ),
        "strongholds": _percentify(_round_frame(strongholds)),
        "top_brands": _round_frame(brands),
        "leads_in_spaces": int((company_rows["rank_in_space"] == 1).sum()),
    }


def cipla_portfolio(context: AnalysisContext) -> dict[str, Any]:
    """Cipla's current cardiac estate: brands, franchises and where they sit."""
    focal = context.sku_facts[context.sku_facts["is_focal"]]
    if focal.empty:
        raise ToolError("No rows for the focal company were found in the dataset.")

    latest = "MAT FEB'26"
    prior = "MAT FEB'25"

    brands = (
        focal.groupby(["brand_root", "CARDIAC SUB SEGMENTS"], as_index=False)
        .agg(value_t2=(latest, "sum"), value_t1=(prior, "sum"), skus=("BRANDS", "nunique"))
        .sort_values("value_t2", ascending=False)
    )
    brands["growth_pct"] = (
        (brands["value_t2"] / brands["value_t1"].where(brands["value_t1"] > 0) - 1.0) * 100.0
    ).fillna(0.0).round(2)

    franchises = (
        focal.groupby("brand_root", as_index=False)
        .agg(value_t2=(latest, "sum"), value_t1=(prior, "sum"))
        .sort_values("value_t2", ascending=False)
        .head(12)
    )
    franchises["growth_pct"] = (
        (franchises["value_t2"] / franchises["value_t1"].where(franchises["value_t1"] > 0) - 1.0)
        * 100.0
    ).fillna(0.0).round(2)

    # Where Cipla is strong, and whether that strength sits in a growing space.
    positions = context.scored[context.scored["level"] == "sub_segment"].sort_values(
        "focal_value_t2", ascending=False
    )
    position_view = positions[
        [
            "space_label",
            "focal_value_t2",
            "focal_share_t2",
            "focal_yoy",
            "value_yoy",
            "real_growth",
            "strategic_verdict",
        ]
    ].head(10)

    molecules = sorted(
        {
            part.strip()
            for signature in focal["molecule_canonical"].astype(str)
            for part in signature.split("+")
            if part.strip()
        }
    )

    return {
        "company": context.focal_label,
        "currency_unit": context.currency_unit,
        "cardiac_value_cr": round(float(focal[latest].sum()), 1),
        "cardiac_share_pct": round(context.totals["focal_share"] * 100.0, 2),
        "growth_pct": round(context.totals["focal_yoy"] * 100.0, 2),
        "market_growth_pct": round(context.totals["market_yoy"] * 100.0, 2),
        "sku_count": int(len(focal)),
        "brand_count": int(focal["BRANDS"].nunique()),
        "umbrella_franchises": _round_frame(
            franchises[["brand_root", "value_t2", "growth_pct"]]
        ),
        "brands_by_sub_segment": _round_frame(brands.head(15)),
        "sub_segment_positions": _percentify(_round_frame(position_view)),
        "molecules_marketed": molecules,
        "molecule_count": len(molecules),
    }


def whitespace_scan(
    context: AnalysisContext, levels: list[str] | None = None, limit: int = 8
) -> dict[str, Any]:
    """Attractive spaces where Cipla is underweight but has a route in."""
    target_levels = levels or ["sub_segment", "molecule_combination", "anchor_molecule"]
    result = find_whitespace(
        context.scored,
        focal_overall_share=context.totals["focal_share"],
        levels=target_levels,
        limit=int(limit),
    )
    if result.empty:
        return {
            "count": 0,
            "spaces": [],
            "note": (
                "No space cleared all three tests at once. Either Cipla is already at or "
                "above fair share in the attractive spaces, or the attractive spaces offer "
                "no molecule or brand route in."
            ),
        }
    return {
        "count": int(len(result)),
        "fair_share_benchmark_pct": round(context.totals["focal_share"] * 100.0, 2),
        "currency_unit": context.currency_unit,
        "spaces": _percentify(_round_frame(result)),
        "method_note": (
            "A space qualifies when its opportunity index is high, Cipla's share is below "
            "three quarters of its therapy-area share, and there is a molecule or brand "
            "route in. The value gap is what reaching fair share alone would be worth."
        ),
    }


def forecast_space_tool(
    context: AnalysisContext, space: str, level: str | None = None, horizon_years: int = 5
) -> dict[str, Any]:
    """Project one space forward three to five years, with a scenario band."""
    row = context.find_space(space, level)
    if row is None:
        raise ToolError(f"No space matches '{space}'.")
    if not 1 <= int(horizon_years) <= 10:
        raise ToolError("horizon_years must be between 1 and 10.")

    forecast = run_forecast(
        row,
        market_cagr=context.totals["market_cagr_2y"],
        framework=context.framework,
        horizon_years=int(horizon_years),
    )
    payload = forecast.to_dict()
    payload["currency_unit"] = context.currency_unit
    payload["verdict"] = (
        "Projected to outperform the Cardiac market"
        if forecast.outperformance_pp > 0
        else "Projected to lag the Cardiac market"
    )
    return payload


def sensitivity_analysis(
    context: AnalysisContext,
    level: str = "molecule_combination",
    top_k: int = 5,
    iterations: int | None = None,
) -> dict[str, Any]:
    """How stable the ranking is when the framework weights are perturbed."""
    if level not in SPACE_LEVELS_ENUM:
        raise ToolError(f"Unknown level '{level}'.")
    result = run_sensitivity(
        context.enriched,
        level=level,
        framework=context.framework,
        iterations=iterations,
        top_k=int(top_k),
    )
    robust = result.stability[result.stability["top_k_frequency"] >= 0.80]
    fragile = result.stability[
        (result.stability["baseline_rank"] <= top_k)
        & (result.stability["top_k_frequency"] < 0.60)
    ]
    return {
        "level": level,
        "iterations": result.iterations,
        "top_k": result.top_k,
        "weight_concentration": result.concentration,
        "stability": result.summary(limit=12),
        "robust_space_count": int(len(robust)),
        "fragile_recommendations": _round_frame(
            fragile[["space_label", "baseline_rank", "top_k_frequency", "worst_rank"]]
        ),
        "method_note": (
            "Every weight block was redrawn from a Dirichlet distribution centred on the "
            "configured values and the market re-scored each time. top_k_frequency is the "
            "share of runs in which the space stayed in the top K. Above 0.8 the "
            "recommendation is robust to how the framework is weighted; below 0.6 it is a "
            "judgement call and should be presented as one."
        ),
    }


def retrieve_external_signals(
    context: AnalysisContext, query: str, top_k: int = 5
) -> dict[str, Any]:
    """Search the curated external-signal corpus. Returns citable passages."""
    if not query.strip():
        raise ToolError("Provide a search query.")
    passages = context.retriever.search(query, top_k=int(top_k))
    return {
        "query": query,
        "hits": [passage.to_dict() for passage in passages],
        "corpus_size": len(context.corpus),
        "citation_note": (
            "Cite these as [S-xx] in the answer. Every external claim needs one; "
            "anything derived from the supplied dataset does not."
        ),
    }


# --- Read-only SQL -----------------------------------------------------------

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|export|install|load|pragma|"
    r"replace|truncate|grant|call|set|reset)\b",
    re.IGNORECASE,
)
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
MAX_SQL_ROWS = 200


def sql_query(context: AnalysisContext, sql: str, limit: int = 50) -> dict[str, Any]:
    """Run a read-only SELECT against the warehouse.

    The escape hatch for questions the purpose-built tools do not cover. It is
    guarded three ways: the statement must start with SELECT or WITH, mutating
    keywords are rejected outright, and the connection itself is opened
    read-only so a bypass of the first two still cannot write.
    """
    statement = sql.strip().rstrip(";")
    if not _ALLOWED_START.match(statement):
        raise ToolError("Only SELECT and WITH statements are permitted.")
    if ";" in statement:
        raise ToolError("Multiple statements are not permitted; send one query.")
    if _FORBIDDEN_SQL.search(statement):
        raise ToolError("The query contains a keyword that could modify the warehouse.")

    row_limit = max(1, min(int(limit), MAX_SQL_ROWS))
    wrapped = f"SELECT * FROM ({statement}) AS agent_query LIMIT {row_limit}"

    connection = duckdb.connect(str(context.warehouse_path), read_only=True)
    try:
        frame = connection.execute(wrapped).fetch_df()
    except duckdb.Error as exc:
        raise ToolError(f"Query failed: {exc}") from exc
    finally:
        connection.close()

    logger.info("tool.sql_query", rows=len(frame), sql=statement[:200])
    return {
        "sql": statement,
        "row_count": int(len(frame)),
        "truncated": bool(len(frame) >= row_limit),
        "columns": list(frame.columns),
        "rows": _round_frame(frame),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def build_tool_specs(context: AnalysisContext) -> dict[str, ToolSpec]:
    """Bind every tool to a context and return the registry."""
    level_enum = {"type": "string", "enum": SPACE_LEVELS_ENUM}

    specs = [
        ToolSpec(
            name="market_overview",
            description=(
                "Size, growth and structure of the whole Cardiac market, plus Cipla's "
                "standing in it. Call this first for any question that needs context, "
                "and whenever a figure has to be expressed as a share of the market."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: market_overview(context),
        ),
        ToolSpec(
            name="rank_opportunity_spaces",
            description=(
                "Rank opportunity spaces at one level. Use rank_by='market_opportunity_index' "
                "to answer 'what are the top opportunities', and "
                "rank_by='cipla_priority_score' to answer 'which should Cipla prioritise'. "
                "Those are different questions and usually have different answers."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "level": {
                        **level_enum,
                        "description": "Granularity. 'molecule_combination' is the launch-decision level; 'sub_segment' is the portfolio level.",
                    },
                    "top_n": {"type": "integer", "minimum": 1, "maximum": 40, "default": 10},
                    "rank_by": {
                        "type": "string",
                        "enum": [
                            "cipla_priority_score",
                            "market_opportunity_index",
                            "value_t2",
                            "value_yoy",
                        ],
                        "default": "cipla_priority_score",
                    },
                    "min_value_cr": {
                        "type": "number",
                        "description": "Optional size floor in INR crore.",
                    },
                },
                "required": ["level"],
            },
            handler=lambda **kwargs: rank_opportunity_spaces(context, **kwargs),
        ),
        ToolSpec(
            name="space_deep_dive",
            description=(
                "Complete evidence card for one space: size, real and volume growth, price "
                "effect, competitive structure, the leading players, Cipla's position and "
                "adjacencies, the external signals attached to it, and the score breakdown. "
                "Call this before recommending or ruling out any space."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "space": {
                        "type": "string",
                        "description": "Space identifier or any distinctive part of its label, e.g. 'CILNIDIPINE + TELMISARTAN'.",
                    },
                    "level": {**level_enum, "description": "Optional, to disambiguate."},
                },
                "required": ["space"],
            },
            handler=lambda **kwargs: space_deep_dive(context, **kwargs),
        ),
        ToolSpec(
            name="compare_spaces",
            description=(
                "Compare two or more spaces side by side and surface the trade-offs between "
                "them - size against growth, growth against competition, attractiveness "
                "against right to win. Use this when asked how a trade-off was resolved."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "spaces": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 6,
                    },
                    "level": level_enum,
                },
                "required": ["spaces"],
            },
            handler=lambda **kwargs: compare_spaces(context, **kwargs),
        ),
        ToolSpec(
            name="competitor_profile",
            description=(
                "Where a named competitor is strong in Cardiac: value, share, growth, its "
                "leading sub-segments and brands. Use when asked how Cipla's position "
                "compares with a specific rival."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name or fragment, e.g. 'Torrent', 'Sun', 'USV'.",
                    }
                },
                "required": ["company"],
            },
            handler=lambda **kwargs: competitor_profile(context, **kwargs),
        ),
        ToolSpec(
            name="cipla_portfolio",
            description=(
                "Cipla's existing cardiac estate: umbrella brand franchises, brands by "
                "sub-segment, molecules already marketed, and whether each strong position "
                "sits in a growing or declining space. Call this before any right-to-win "
                "claim."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: cipla_portfolio(context),
        ),
        ToolSpec(
            name="whitespace_scan",
            description=(
                "Attractive spaces where Cipla is materially below its fair share but has a "
                "credible route in via molecule adjacency or an extendable brand. This is "
                "the tool for the underpenetration question."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": level_enum},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                },
                "required": [],
            },
            handler=lambda **kwargs: whitespace_scan(context, **kwargs),
        ),
        ToolSpec(
            name="forecast_space",
            description=(
                "Project one space three to five years forward with base, bull and bear "
                "cases, and state whether it outperforms the market. Use for any claim "
                "about future performance; never estimate a forward number yourself."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "space": {"type": "string"},
                    "level": level_enum,
                    "horizon_years": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                    },
                },
                "required": ["space"],
            },
            handler=lambda **kwargs: forecast_space_tool(context, **kwargs),
        ),
        ToolSpec(
            name="sensitivity_analysis",
            description=(
                "Re-score the market hundreds of times under randomised framework weights "
                "and report how often each space stays in the top K. Call this before "
                "presenting a final recommendation, and whenever asked how sensitive the "
                "answer is to the weighting."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "level": level_enum,
                    "top_k": {"type": "integer", "minimum": 3, "maximum": 10, "default": 5},
                    "iterations": {"type": "integer", "minimum": 50, "maximum": 2000},
                },
                "required": [],
            },
            handler=lambda **kwargs: sensitivity_analysis(context, **kwargs),
        ),
        ToolSpec(
            name="retrieve_external_signals",
            description=(
                "Search the curated corpus of external signals - epidemiology, clinical "
                "guidelines, pricing regulation, innovation pipeline, environmental "
                "evidence. Returns citable passages with identifiers. Every claim about "
                "the world outside the dataset must come from here."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
                "required": ["query"],
            },
            handler=lambda **kwargs: retrieve_external_signals(context, **kwargs),
        ),
        ToolSpec(
            name="sql_query",
            description=(
                "Read-only SELECT against the warehouse for questions the other tools do "
                "not cover. Tables: sku_facts, space_facts, space_membership, company_facts, "
                "brand_facts, glossary. Prefer a purpose-built tool when one fits - they "
                "return interpreted metrics, this returns raw rows."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A single SELECT or WITH statement."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SQL_ROWS, "default": 50},
                },
                "required": ["sql"],
            },
            handler=lambda **kwargs: sql_query(context, **kwargs),
        ),
    ]

    enabled = set(context.framework.get_path("agent.enabled_tools", []) or [])
    registry = {spec.name: spec for spec in specs if not enabled or spec.name in enabled}
    logger.info("tools.registered", tools=sorted(registry))
    return registry


__all__ = [
    "MAX_SQL_ROWS",
    "RANKING_COLUMNS",
    "SPACE_LEVELS_ENUM",
    "ToolError",
    "ToolSpec",
    "build_tool_specs",
]
