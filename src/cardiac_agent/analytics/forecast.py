"""Three-to-five year projection.

The case asks which spaces will "outperform the broader Cardiac market over the
next 3-5 years". Answering that honestly means projecting, and projecting from
two years of history means being explicit about the assumptions rather than
hiding them behind a model.

The method, and why:

1. **Start from demand, not price.** The base rate blends constant-price growth
   and volume growth, with reported value growth given the smallest weight.
   Price gains do not compound the way prescription volume does, and India's
   price-controlled cardiac basket makes that doubly true.

2. **Mean-revert.** Excess growth over the therapy area decays geometrically.
   Nothing grows at forty-five per cent for five years; assuming it does is how
   forecasts produce indefensible numbers. ``growth_decay`` is the fraction of
   the excess that survives each year.

3. **Tilt for external signals, within bounds.** The RAG layer supplies a
   multiplier in a narrow band. Secondary research can shade the view; it can
   never overturn what the audit shows.

4. **Show the band.** Bull and bear cases shift the rate by a configured spread
   so a reader sees the uncertainty rather than a single false-precision figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import FrameworkConfig, get_framework
from .metrics import EPSILON

#: How the base growth rate is composed. Demand-led measures dominate.
BASE_RATE_WEIGHTS: dict[str, float] = {
    "real_growth": 0.40,
    "volume_growth": 0.30,
    "value_cagr_2y": 0.20,
    "momentum": 0.10,
}


@dataclass
class Forecast:
    """A single space's projection, with its assumptions attached."""

    space_id: str
    space_label: str
    level: str
    base_value_cr: float
    horizon_years: int
    base_cagr: float
    projected_value_cr: float
    bull_value_cr: float
    bear_value_cr: float
    market_cagr: float
    outperformance_pp: float
    trend_multiplier: float
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "space_label": self.space_label,
            "level": self.level,
            "base_value_cr": round(self.base_value_cr, 1),
            "horizon_years": self.horizon_years,
            "base_cagr_pct": round(self.base_cagr * 100.0, 2),
            "projected_value_cr": round(self.projected_value_cr, 1),
            "bull_value_cr": round(self.bull_value_cr, 1),
            "bear_value_cr": round(self.bear_value_cr, 1),
            "market_cagr_pct": round(self.market_cagr * 100.0, 2),
            "outperformance_pp": round(self.outperformance_pp, 2),
            "trend_multiplier": round(self.trend_multiplier, 3),
            "assumptions": self.assumptions,
        }


def _compound_with_decay(
    base_value: float,
    start_rate: float,
    market_rate: float,
    years: int,
    decay: float,
) -> tuple[float, float]:
    """Compound forward, decaying the excess over market growth each year.

    Returns ``(terminal_value, effective_cagr)``.
    """
    value = base_value
    excess = start_rate - market_rate
    for _ in range(years):
        rate = market_rate + excess
        value *= 1.0 + rate
        excess *= decay
    if base_value > EPSILON and value > EPSILON:
        effective = (value / base_value) ** (1.0 / years) - 1.0
    else:
        effective = 0.0
    return value, effective


def forecast_space(
    row: pd.Series,
    market_cagr: float,
    *,
    framework: FrameworkConfig | None = None,
    horizon_years: int | None = None,
) -> Forecast:
    """Project one opportunity space forward.

    Args:
        row: A scored space row.
        market_cagr: Therapy-area growth rate the space reverts towards.
        framework: Parsed configuration.
        horizon_years: Override the configured horizon (the case asks for 3-5).
    """
    framework = framework or get_framework()
    horizon = int(horizon_years or framework.get_path("forecast.horizon_years", 5))
    decay = float(framework.get_path("forecast.growth_decay", 0.72))
    cap = float(framework.get_path("forecast.max_projected_cagr", 0.45))
    floor = float(framework.get_path("forecast.min_projected_cagr", -0.15))
    spread = float(framework.get_path("forecast.scenario_spread_pp", 4.0)) / 100.0

    blended = sum(
        float(row.get(metric, 0.0)) * weight for metric, weight in BASE_RATE_WEIGHTS.items()
    )
    multiplier = float(row.get("trend_multiplier", 1.0) or 1.0)
    start_rate = max(floor, min(cap, blended * multiplier))

    base_value = float(row.get("value_t2", 0.0))
    projected, effective = _compound_with_decay(base_value, start_rate, market_cagr, horizon, decay)
    bull, _ = _compound_with_decay(
        base_value, min(cap, start_rate + spread), market_cagr, horizon, decay
    )
    bear, _ = _compound_with_decay(
        base_value, max(floor, start_rate - spread), market_cagr, horizon, decay
    )

    assumptions = [
        "Base rate blends constant-price growth (40%), volume growth (30%), "
        "two-year value CAGR (20%) and three-month momentum (10%).",
        f"Excess growth over the market decays {int((1 - decay) * 100)}% per year "
        f"towards the therapy-area rate of {market_cagr * 100:.1f}%.",
        f"External-signal multiplier applied: {multiplier:.2f}x.",
        f"Rate capped to the band [{floor * 100:.0f}%, {cap * 100:.0f}%].",
        f"Bull and bear cases shift the starting rate by {spread * 100:.0f} percentage points.",
    ]

    return Forecast(
        space_id=str(row.get("space_id", "")),
        space_label=str(row.get("space_label", "")),
        level=str(row.get("level", "")),
        base_value_cr=base_value,
        horizon_years=horizon,
        base_cagr=effective,
        projected_value_cr=projected,
        bull_value_cr=bull,
        bear_value_cr=bear,
        market_cagr=market_cagr,
        outperformance_pp=(effective - market_cagr) * 100.0,
        trend_multiplier=multiplier,
        assumptions=assumptions,
    )


def forecast_spaces(
    scored: pd.DataFrame,
    market_cagr: float,
    *,
    framework: FrameworkConfig | None = None,
    horizon_years: int | None = None,
) -> pd.DataFrame:
    """Project every scored space and return the results as a frame."""
    framework = framework or get_framework()
    records = [
        forecast_space(row, market_cagr, framework=framework, horizon_years=horizon_years).to_dict()
        for _, row in scored.iterrows()
    ]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame
    return frame.drop(columns=["assumptions"]).assign(
        outperforms_market=lambda f: f["outperformance_pp"] > 0.0
    )


__all__ = ["BASE_RATE_WEIGHTS", "Forecast", "forecast_space", "forecast_spaces"]
