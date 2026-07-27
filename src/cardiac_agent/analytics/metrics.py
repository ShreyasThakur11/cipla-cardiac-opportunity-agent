"""Growth, demand and momentum metrics.

The workbook gives three parallel views of the same market and the glossary is
explicit about what each one means. Using them together is the difference
between a defensible answer and a naive one:

* ``MAT`` is reported value. It moves on both price and demand.
* ``MAT CP`` holds prices at the prior year's level, so its growth is demand
  growth. The gap between the two *is* the price contribution.
* ``QTY MAT`` is units consumed, which validates the constant-price read and
  catches a space that is growing on trade loading rather than prescriptions.

A space growing 12 per cent on value but 1 per cent on volume is a price story
and will not compound for five years. The scoring engine weights the
constant-price and volume reads above headline value for exactly that reason.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Guard for ratio denominators. Below this a space is too small for a
#: percentage to carry information, so the metric is reported as zero rather
#: than as a spurious four-digit growth rate.
EPSILON = 1e-9

#: Growth rates are clipped to this band. A pack that went from 0.001 to 0.5
#: crore is a rounding artefact, not a 50,000 per cent opportunity.
GROWTH_CLIP = (-1.0, 3.0)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise division that returns 0.0 instead of inf or NaN."""
    denom = denominator.astype(float)
    result = numerator.astype(float).divide(denom.where(denom.abs() > EPSILON))
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _growth(later: pd.Series, earlier: pd.Series) -> pd.Series:
    """Period-on-period growth, clipped to a plausible band."""
    return (_safe_ratio(later, earlier) - 1.0).where(earlier.abs() > EPSILON, 0.0).clip(*GROWTH_CLIP)


def _cagr(later: pd.Series, earlier: pd.Series, years: float) -> pd.Series:
    """Compound annual growth rate over ``years``, clipped to the same band."""
    ratio = _safe_ratio(later, earlier)
    positive = ratio.where(ratio > EPSILON)
    result = np.power(positive, 1.0 / years) - 1.0
    return pd.Series(result, index=later.index).fillna(0.0).clip(*GROWTH_CLIP)


def add_growth_metrics(spaces: pd.DataFrame, *, months_per_period: int = 12) -> pd.DataFrame:
    """Attach every growth, demand and momentum metric to the space frame.

    Args:
        spaces: Output of :func:`~cardiac_agent.ingestion.spaces.build_all_spaces`.
        months_per_period: Months in a MAT window. Twelve, unless the
            organisers change the reporting convention.

    Returns:
        A copy of ``spaces`` with the derived metric columns appended.
    """
    out = spaces.copy()

    # --- Headline value ---------------------------------------------------
    out["value_yoy"] = _growth(out["value_t2"], out["value_t1"])
    out["value_cagr_2y"] = _cagr(out["value_t2"], out["value_t0"], years=2.0)
    out["absolute_growth_cr"] = (out["value_t2"] - out["value_t1"]).astype(float)

    # --- Demand, stripped of price ---------------------------------------
    # MAT CP for the latest period is stated at the previous year's prices, so
    # comparing it against the previous year's reported MAT isolates real
    # demand growth. This is the organisers' own definition, not our invention.
    out["real_growth"] = _growth(out["cp_t2"], out["value_t1"])
    out["real_growth_prior"] = _growth(out["cp_t1"], out["value_t0"])
    out["volume_growth"] = _growth(out["qty_t2"], out["qty_t1"])
    out["volume_cagr_2y"] = _cagr(out["qty_t2"], out["qty_t0"], years=2.0)

    # Price contribution: everything in the value move that demand does not
    # explain. Positive means price is doing the work; sustained positive
    # values alongside flat volume is the classic late-stage-brand pattern.
    out["price_effect"] = (out["value_yoy"] - out["real_growth"]).astype(float)

    # --- Momentum ---------------------------------------------------------
    # The last three months annualised, compared with the trailing twelve.
    # This is the earliest signal available that a trend is bending, and it is
    # why the dataset ships December, January and February separately.
    annualised = out["recent_3m_sales"].astype(float) * (months_per_period / 3.0)
    out["run_rate_annualised"] = annualised
    out["momentum"] = (_safe_ratio(annualised, out["value_t2"]) - 1.0).where(
        out["value_t2"].abs() > EPSILON, 0.0
    ).clip(-0.9, 1.5)

    # --- Realised price ---------------------------------------------------
    out["price_per_unit_t2"] = _safe_ratio(out["value_t2"], out["qty_t2"])
    out["price_per_unit_t1"] = _safe_ratio(out["value_t1"], out["qty_t1"])
    out["price_per_unit_change"] = _growth(out["price_per_unit_t2"], out["price_per_unit_t1"])

    # --- Focal player (Cipla) --------------------------------------------
    out["focal_share_t2"] = _safe_ratio(out["focal_value_t2"], out["value_t2"])
    out["focal_share_t1"] = _safe_ratio(out["focal_value_t1"], out["value_t1"])
    out["focal_share_delta_pp"] = (out["focal_share_t2"] - out["focal_share_t1"]) * 100.0
    out["focal_yoy"] = _growth(out["focal_value_t2"], out["focal_value_t1"])
    # Positive means Cipla is outgrowing the space and taking share.
    out["focal_growth_gap"] = (out["focal_yoy"] - out["value_yoy"]).where(
        out["focal_value_t1"].abs() > EPSILON, 0.0
    )
    out["focal_present"] = out["focal_value_t2"] > EPSILON

    # --- Convenience shares ----------------------------------------------
    segment_total = out.loc[out["level"] == "segment", "value_t2"].sum()
    out["share_of_cardiac_pct"] = _safe_ratio(
        out["value_t2"], pd.Series(segment_total, index=out.index)
    ) * 100.0

    return out


def market_totals(spaces: pd.DataFrame) -> dict[str, float]:
    """Therapy-area totals, computed from the segment level only.

    Summing any other level would double count, because a SKU belongs to
    several spaces at once.
    """
    segments = spaces[spaces["level"] == "segment"]
    total_t0 = float(segments["value_t0"].sum())
    total_t1 = float(segments["value_t1"].sum())
    total_t2 = float(segments["value_t2"].sum())
    cp_t2 = float(segments["cp_t2"].sum())
    qty_t1 = float(segments["qty_t1"].sum())
    qty_t2 = float(segments["qty_t2"].sum())
    focal_t1 = float(segments["focal_value_t1"].sum())
    focal_t2 = float(segments["focal_value_t2"].sum())

    def ratio(later: float, earlier: float) -> float:
        return (later / earlier - 1.0) if abs(earlier) > EPSILON else 0.0

    return {
        "market_value_t0": total_t0,
        "market_value_t1": total_t1,
        "market_value_t2": total_t2,
        "market_yoy": ratio(total_t2, total_t1),
        "market_cagr_2y": (total_t2 / total_t0) ** 0.5 - 1.0 if total_t0 > EPSILON else 0.0,
        "market_real_growth": ratio(cp_t2, total_t1),
        "market_volume_growth": ratio(qty_t2, qty_t1),
        "market_price_effect": ratio(total_t2, total_t1) - ratio(cp_t2, total_t1),
        "focal_value_t2": focal_t2,
        "focal_share": focal_t2 / total_t2 if total_t2 > EPSILON else 0.0,
        "focal_yoy": ratio(focal_t2, focal_t1),
    }


__all__ = ["EPSILON", "add_growth_metrics", "market_totals"]
