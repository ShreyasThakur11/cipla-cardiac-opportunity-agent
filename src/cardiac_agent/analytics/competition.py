"""Competitive structure.

Growth alone is a trap. A space can grow twenty per cent a year and still be
uninvestable because one player holds sixty per cent of it and defends with a
field force three times your size. These metrics answer the second half of the
question the case asks: not "is it growing" but "can anyone new take share".

Five readings, each catching a different kind of closed market:

``hhi``            Herfindahl-Hirschman index. Above 2500 is concentrated.
``leader_share``   One dominant brand owner is harder to displace than three
                   evenly matched ones with the same combined share.
``top3_share``     Distinguishes an oligopoly from a genuine long tail.
``crowding``       Players per 100 crore. A fragmented space with ninety
                   entrants is not open, it is commoditised.
``share_churn``    How much share actually moved last year. A space where
                   nothing moves is closed regardless of what the HHI says.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import EPSILON

#: Conventional competition-authority thresholds, used for labelling only.
HHI_CONCENTRATED = 2500.0
HHI_MODERATE = 1500.0


def _concentration_label(hhi: float) -> str:
    if hhi >= HHI_CONCENTRATED:
        return "Concentrated"
    if hhi >= HHI_MODERATE:
        return "Moderately concentrated"
    return "Fragmented"


def _per_space(group: pd.DataFrame) -> pd.Series:
    """Compute the competitive profile for one space from its company rows."""
    value_t2 = group["value_t2"].to_numpy(dtype=float)
    value_t1 = group["value_t1"].to_numpy(dtype=float)
    total_t2 = float(value_t2.sum())
    total_t1 = float(value_t1.sum())

    active = value_t2 > EPSILON
    n_players = int(active.sum())

    if total_t2 <= EPSILON or n_players == 0:
        return pd.Series(
            {
                "n_players": n_players,
                "hhi": 10_000.0,
                "leader_share": 1.0,
                "top3_share": 1.0,
                "top5_share": 1.0,
                "effective_competitors": 0.0,
                "leader_company": "",
                "share_churn": 0.0,
                "new_entrant_count": 0,
                "mnc_share": 0.0,
            }
        )

    shares = np.sort(value_t2[active] / total_t2)[::-1]
    hhi = float(np.sum((shares * 100.0) ** 2))
    leader_index = int(np.argmax(value_t2))

    # Share churn: total absolute share movement between the two MATs. Halved
    # so that one point moving from A to B counts as one point, not two.
    if total_t1 > EPSILON:
        shares_t1 = value_t1 / total_t1
        shares_t2 = value_t2 / total_t2
        churn = float(np.abs(shares_t2 - shares_t1).sum() / 2.0)
    else:
        churn = 0.0

    new_entrants = int(((value_t1 <= EPSILON) & (value_t2 > EPSILON)).sum())
    mnc_flags = group.get("is_mnc")
    mnc_share = (
        float(value_t2[mnc_flags.fillna(False).to_numpy(dtype=bool)].sum() / total_t2)
        if mnc_flags is not None
        else 0.0
    )

    return pd.Series(
        {
            "n_players": n_players,
            "hhi": hhi,
            "leader_share": float(shares[0]),
            "top3_share": float(shares[:3].sum()),
            "top5_share": float(shares[:5].sum()),
            # Inverse HHI: how many equally sized players the space behaves like.
            "effective_competitors": float(10_000.0 / hhi) if hhi > 0 else 0.0,
            "leader_company": str(group["company_clean"].to_numpy()[leader_index]),
            "share_churn": churn,
            "new_entrant_count": new_entrants,
            "mnc_share": mnc_share,
        }
    )


def add_competition_metrics(spaces: pd.DataFrame, company_facts: pd.DataFrame) -> pd.DataFrame:
    """Attach competitive-structure metrics to the space frame.

    Args:
        spaces: Space frame, ideally already carrying growth metrics.
        company_facts: One row per company per space, from the warehouse.

    Returns:
        A copy of ``spaces`` with the competition columns appended.
    """
    profile = (
        company_facts.groupby(["level", "space_id"], group_keys=True)
        .apply(_per_space, include_groups=False)
        .reset_index()
    )

    out = spaces.merge(profile, on=["level", "space_id"], how="left")

    out["n_players"] = out["n_players"].fillna(0).astype(int)
    out["hhi"] = out["hhi"].fillna(10_000.0).astype(float)
    for column in ("leader_share", "top3_share", "top5_share"):
        out[column] = out[column].fillna(1.0).astype(float)
    out["effective_competitors"] = out["effective_competitors"].fillna(0.0).astype(float)
    out["leader_company"] = out["leader_company"].fillna("")
    out["share_churn"] = out["share_churn"].fillna(0.0).astype(float)
    out["new_entrant_count"] = out["new_entrant_count"].fillna(0).astype(int)
    out["mnc_share"] = out["mnc_share"].fillna(0.0).astype(float)

    # Players per 100 crore of market. High values mean the space has already
    # been discovered and is being fought on price.
    hundreds = (out["value_t2"].astype(float) / 100.0).where(out["value_t2"] > EPSILON)
    out["crowding"] = (out["n_players"] / hundreds).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Price erosion as a positive number, so a bigger value is unambiguously
    # worse. Spaces where price is additive score zero rather than negative.
    out["price_erosion"] = (-out["price_effect"]).clip(lower=0.0)

    out["concentration_label"] = out["hhi"].map(_concentration_label)
    out["is_structurally_closed"] = (out["n_players"] < 3) | (out["leader_share"] >= 0.80)

    return out


def top_competitors(
    company_facts: pd.DataFrame, level: str, space_id: str, limit: int = 8
) -> pd.DataFrame:
    """The leading players in one space, ordered by latest value."""
    subset = company_facts[
        (company_facts["level"] == level) & (company_facts["space_id"] == space_id)
    ].copy()
    if subset.empty:
        return subset
    subset["yoy"] = (
        (
            subset["value_t2"].divide(subset["value_t1"].where(subset["value_t1"].abs() > EPSILON))
            - 1.0
        )
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    columns = ["company_clean", "value_t2", "share_t2", "yoy", "rank_in_space"]
    return subset.sort_values("value_t2", ascending=False).head(limit)[columns]


__all__ = [
    "HHI_CONCENTRATED",
    "HHI_MODERATE",
    "add_competition_metrics",
    "top_competitors",
]
