"""Underpenetrated attractive spaces.

The case asks a question most prioritisation exercises skip: "which attractive
opportunity spaces appear underpenetrated by Cipla today despite strong
long-term potential". That is not the top of the priority list - those are
places Cipla is already positioned. It is the gap between where the market is
going and where Cipla currently sits.

A space qualifies as whitespace when three things are true at once:

1. The market opportunity index is high - it is worth someone's while.
2. Cipla's share is materially below its share of the therapy area overall -
   it is genuinely underpenetrated rather than simply small.
3. There is a credible route in - molecule adjacency or an extendable brand.

Point three is what separates a target from a wish. A high-growth space where
Cipla has no molecule, no brand and no prescriber relationship is not
underpenetrated; it is somebody else's market.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class WhitespaceCriteria:
    """Thresholds that define whitespace, exposed so they can be challenged."""

    min_moi: float = 55.0
    #: Multiple of Cipla's therapy-area share below which a space counts as
    #: underpenetrated. 0.75 means "less than three quarters of its fair share".
    penetration_ratio: float = 0.75
    #: At least one route in must clear its bar.
    min_molecule_adjacency: float = 0.30
    min_brand_franchise: float = 0.60
    #: Ignore spaces too small to be worth a launch.
    min_value_cr: float = 150.0


def find_whitespace(
    scored: pd.DataFrame,
    focal_overall_share: float,
    *,
    criteria: WhitespaceCriteria | None = None,
    levels: list[str] | None = None,
    limit: int = 12,
) -> pd.DataFrame:
    """Identify attractive spaces where the focal company is underweight.

    Args:
        scored: Output of :func:`~.scoring.build_scorecard`.
        focal_overall_share: Cipla's share of the whole Cardiac market, used as
            the fair-share benchmark.
        criteria: Threshold overrides.
        levels: Restrict to these space levels.
        limit: Maximum rows returned.

    Returns:
        Matching spaces ordered by the size of the value gap, with columns
        explaining why each one qualified and what the route in would be.
    """
    criteria = criteria or WhitespaceCriteria()
    frame = scored.copy()
    if levels:
        frame = frame[frame["level"].isin(levels)]

    fair_share = focal_overall_share * criteria.penetration_ratio

    has_route = (
        frame["rtw_molecule_adjacency"] >= criteria.min_molecule_adjacency
    ) | (frame["rtw_brand_franchise"] >= criteria.min_brand_franchise)

    qualifies = (
        (frame["market_opportunity_index"] >= criteria.min_moi)
        & (frame["focal_share_t2"] < fair_share)
        & (frame["value_t2"] >= criteria.min_value_cr)
        & has_route
    )

    result = frame[qualifies].copy()
    if result.empty:
        logger.info("whitespace.none", fair_share=fair_share, min_moi=criteria.min_moi)
        return result

    # The prize: value Cipla would hold if it merely reached its fair share.
    result["fair_share_value_cr"] = result["value_t2"] * focal_overall_share
    result["value_gap_cr"] = result["fair_share_value_cr"] - result["focal_value_t2"]
    result["penetration_index"] = (
        result["focal_share_t2"] / focal_overall_share if focal_overall_share else 0.0
    )

    def _route(row: pd.Series) -> str:
        routes: list[str] = []
        if row["rtw_brand_franchise"] >= 1.0 and row.get("adjacent_cipla_brands"):
            routes.append(f"extend {row['adjacent_cipla_brands']}")
        elif row["rtw_brand_franchise"] >= criteria.min_brand_franchise:
            routes.append("extend an adjacent Cipla brand")
        if row["rtw_molecule_adjacency"] >= criteria.min_molecule_adjacency:
            routes.append(
                f"{row['rtw_molecule_adjacency'] * 100:.0f}% of the space's molecules "
                "are already in the Cipla portfolio"
            )
        if row["rtw_detailing_adjacency"] > 0.02:
            routes.append("field force already covers this sub-segment")
        return "; ".join(routes) if routes else "no obvious route in"

    result["route_to_win"] = result.apply(_route, axis=1)

    columns = [
        "level",
        "space_id",
        "space_label",
        "value_t2",
        "value_yoy",
        "real_growth",
        "market_opportunity_index",
        "right_to_win_score",
        "cipla_priority_score",
        "focal_value_t2",
        "focal_share_t2",
        "penetration_index",
        "fair_share_value_cr",
        "value_gap_cr",
        "route_to_win",
        "leader_company",
        "leader_share",
        "hhi",
        "strategic_verdict",
    ]
    available = [column for column in columns if column in result.columns]
    ordered = result.sort_values("value_gap_cr", ascending=False).head(limit)[available]

    logger.info("whitespace.found", count=len(ordered), fair_share=round(fair_share, 5))
    return ordered


__all__ = ["WhitespaceCriteria", "find_whitespace"]
