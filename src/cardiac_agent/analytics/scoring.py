"""The prioritisation framework.

Two scores, deliberately kept apart:

**Market Opportunity Index (MOI)** - how good the space is, for anybody. Built
from market attractiveness, future potential and competitive headroom. Cipla
does not appear in it. This is what answers "what are the top opportunities the
agent identified".

**Cipla Priority Score (CPS)** - MOI passed through a right-to-win gate. This
is what answers "which two or three should Cipla actually prioritise".

Splitting them is the whole design. A single blended score would quietly bury
the trade-off the case asks us to expose; two scores make the tension visible.
A space with a high MOI and a low CPS is not a miss, it is a space where
someone else will win - and naming those explicitly is as useful as naming the
targets.

Normalisation is percentile-based and computed **within a level**. Comparing a
three-member segment against a hundred-and-fifty-member molecule list on a
common min-max scale would say more about the size of the list than about the
market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config import FrameworkConfig, get_framework
from ..logging_config import get_logger

logger = get_logger(__name__)

#: Metrics where a smaller raw value is better, so the percentile is flipped.
INVERTED_METRICS: frozenset[str] = frozenset({"hhi", "leader_share", "crowding", "price_erosion"})

#: Source column for each configured metric name.
METRIC_COLUMNS: dict[str, str] = {
    # market_attractiveness
    "size_cr": "value_t2",
    "absolute_growth_cr": "absolute_growth_cr",
    "value_cagr": "value_cagr_2y",
    # future_potential
    "real_growth": "real_growth",
    "volume_growth": "volume_growth",
    "momentum": "momentum",
    "external_trend": "trend_multiplier",
    # competitive_headroom
    "hhi": "hhi",
    "leader_share": "leader_share",
    "crowding": "crowding",
    "price_erosion": "price_erosion",
    # right_to_win
    "current_share": "rtw_current_share",
    "share_momentum": "rtw_share_momentum",
    "molecule_adjacency": "rtw_molecule_adjacency",
    "brand_franchise": "rtw_brand_franchise",
    "detailing_adjacency": "rtw_detailing_adjacency",
    "formulation_fit": "rtw_formulation_fit",
}

PILLARS: tuple[str, ...] = (
    "market_attractiveness",
    "future_potential",
    "competitive_headroom",
    "right_to_win",
)


@dataclass
class ScoreResult:
    """A completed scoring run, with everything needed to defend it."""

    scored: pd.DataFrame
    weights: dict[str, Any]
    excluded: pd.DataFrame
    notes: list[str] = field(default_factory=list)

    def top(self, level: str, by: str = "cipla_priority_score", limit: int = 5) -> pd.DataFrame:
        """Highest-ranked spaces at one level."""
        subset = self.scored[self.scored["level"] == level]
        return subset.sort_values(by, ascending=False).head(limit)


def _winsorise(series: pd.Series, lower_pct: float, upper_pct: float) -> pd.Series:
    """Clip a series to a percentile band before ranking.

    One pack that grew from 0.001 to 5 crore should not compress every other
    space into the bottom decile of the growth distribution.
    """
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return series.fillna(0.0)
    low = float(np.percentile(clean, lower_pct))
    high = float(np.percentile(clean, upper_pct))
    if high <= low:
        return series.fillna(low)
    return series.fillna(low).clip(low, high)


def _percentile_score(series: pd.Series, *, invert: bool) -> pd.Series:
    """Rank a metric to 0-100 within its group.

    Percentile rank is used rather than min-max because pharmaceutical audit
    metrics are heavily skewed: a handful of molecules carry most of the value
    and would otherwise dominate the scale.
    """
    if series.nunique(dropna=False) <= 1:
        # A constant metric carries no information; give every space the
        # midpoint rather than an arbitrary zero or one hundred.
        return pd.Series(50.0, index=series.index)
    ranked = series.rank(pct=True, method="average") * 100.0
    return (100.0 - ranked) if invert else ranked


def metric_percentiles(frame: pd.DataFrame, framework: FrameworkConfig) -> pd.DataFrame:
    """Percentile-score every metric used by the framework.

    Split out from the weighted combination deliberately: percentiles do not
    depend on the weights, so the sensitivity analysis can compute this once
    and then re-weight hundreds of times. Recomputing it per iteration turned a
    sub-second analysis into a minute-long one.
    """
    winsorise = framework.get_path("scoring.winsorise", {}) or {}
    lower_pct = float(winsorise.get("lower_pct", 2.0))
    upper_pct = float(winsorise.get("upper_pct", 98.0))

    scores = pd.DataFrame(index=frame.index)
    for pillar in PILLARS:
        for metric in framework.require(f"scoring.{pillar}"):
            key = f"score__{pillar}__{metric}"
            if key in scores.columns:
                continue
            column = METRIC_COLUMNS.get(metric)
            if column is None or column not in frame.columns:
                raise KeyError(
                    f"Metric '{metric}' in scoring.{pillar} maps to column "
                    f"'{column}', which is not present. Available columns include "
                    f"{sorted(frame.columns)[:12]}..."
                )
            raw = pd.to_numeric(frame[column], errors="coerce")
            clipped = _winsorise(raw, lower_pct, upper_pct)
            # Ranking is done inside each level so like is compared with like.
            scores[key] = clipped.groupby(frame["level"]).transform(
                lambda values, inverted=metric in INVERTED_METRICS: _percentile_score(
                    values, invert=inverted
                )
            )
    return scores


def _pillar_scores(
    frame: pd.DataFrame,
    framework: FrameworkConfig,
    percentiles: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Combine metric percentiles into the four pillar scores."""
    scores = percentiles if percentiles is not None else metric_percentiles(frame, framework)
    contributions = scores.copy()
    weights_used: dict[str, dict[str, float]] = {}

    for pillar in PILLARS:
        metric_weights: dict[str, float] = framework.require(f"scoring.{pillar}")
        total_weight = sum(metric_weights.values())
        if not np.isclose(total_weight, 1.0, atol=1e-6):
            raise ValueError(
                f"Weights for scoring.{pillar} sum to {total_weight:.4f}, expected 1.0. "
                "Fix config/settings.yaml."
            )
        weights_used[pillar] = dict(metric_weights)

        pillar_total = pd.Series(0.0, index=frame.index)
        for metric, weight in metric_weights.items():
            pillar_total = pillar_total + contributions[f"score__{pillar}__{metric}"] * weight
        contributions[f"pillar__{pillar}"] = pillar_total

    return contributions, weights_used


def _right_to_win_gate(rtw: pd.Series, framework: FrameworkConfig) -> pd.Series:
    """Convert the right-to-win score into a multiplier on market opportunity.

    The curve exponent above 1.0 makes weak right-to-win hurt more than
    linearly. That is intentional: in a market where Cipla holds 1.7 per cent
    overall, the failure mode to guard against is chasing growth into spaces
    where it has no structural advantage.
    """
    gate = framework.get_path("scoring.rtw_gate", {}) or {}
    floor = float(gate.get("floor", 0.35))
    ceiling = float(gate.get("ceiling", 1.0))
    curve = float(gate.get("curve", 1.35))
    normalised = (rtw.clip(0.0, 100.0) / 100.0) ** curve
    return floor + (ceiling - floor) * normalised


def build_scorecard(
    spaces: pd.DataFrame,
    *,
    framework: FrameworkConfig | None = None,
    weight_overrides: dict[str, dict[str, float]] | None = None,
    min_value_cr: float | None = None,
    min_players: int | None = None,
    levels: list[str] | None = None,
    percentiles: pd.DataFrame | None = None,
) -> ScoreResult:
    """Score every opportunity space.

    Args:
        spaces: Space frame carrying growth, competition and right-to-win
            metrics, plus a ``trend_multiplier`` column.
        framework: Parsed configuration. Defaults to the project config.
        weight_overrides: Replacement weight blocks, used by the sensitivity
            analysis and by a reviewer asking "what if growth mattered more".
        min_value_cr: Size floor. Defaults to ``market.min_space_value_cr``.
        min_players: Minimum active competitors. Defaults to
            ``market.min_players``. Lowered by tests that score small synthetic
            markets, where the structural-closure filter would remove everything.
        levels: Restrict scoring to these levels.
        percentiles: Pre-computed metric percentiles, indexed like ``spaces``.
            Supplied by the sensitivity analysis so hundreds of re-weightings
            share one ranking pass.

    Returns:
        A :class:`ScoreResult` holding the scored frame, the weights actually
        used, and the spaces excluded by the size and player-count filters.
    """
    framework = framework or get_framework()
    if weight_overrides:
        merged = FrameworkConfig({**framework})
        scoring_block = {**framework.require("scoring")}
        for pillar, block in weight_overrides.items():
            scoring_block[pillar] = block
        merged["scoring"] = scoring_block
        framework = merged

    frame = spaces.copy()
    if levels:
        frame = frame[frame["level"].isin(levels)]

    if "trend_multiplier" not in frame.columns:
        # No external-signal linkage has been run. Neutral multiplier keeps the
        # framework intact and the absence is recorded in the notes.
        frame["trend_multiplier"] = 1.0

    notes: list[str] = []
    floor_value = (
        float(min_value_cr)
        if min_value_cr is not None
        else float(framework.get_path("market.min_space_value_cr", 100.0))
    )
    player_floor = (
        int(min_players)
        if min_players is not None
        else int(framework.get_path("market.min_players", 3))
    )

    too_small = frame["value_t2"] < floor_value
    too_closed = frame["n_players"].fillna(0) < player_floor
    drop_mask = too_small | too_closed

    excluded = frame[drop_mask].copy()
    excluded["exclusion_reason"] = np.where(
        too_small[drop_mask].to_numpy(),
        f"below size floor of {floor_value:.0f} crore",
        f"fewer than {player_floor} active players",
    )
    frame = frame[~drop_mask].copy()

    if frame.empty:
        raise ValueError(
            "No opportunity spaces survived the filters. Lower "
            "market.min_space_value_cr or check that the warehouse was built."
        )

    notes.append(
        f"{len(excluded)} spaces excluded: below {floor_value:.0f} crore or fewer "
        f"than {player_floor} active players."
    )

    prepared = percentiles.loc[frame.index] if percentiles is not None else None
    contributions, weights_used = _pillar_scores(frame, framework, prepared)
    frame = pd.concat([frame, contributions], axis=1)

    moi_weights: dict[str, float] = framework.require("scoring.moi_weights")
    moi_total = sum(moi_weights.values())
    if not np.isclose(moi_total, 1.0, atol=1e-6):
        raise ValueError(
            f"scoring.moi_weights sums to {moi_total:.4f}, expected 1.0. Fix config/settings.yaml."
        )

    frame["market_opportunity_index"] = sum(
        frame[f"pillar__{pillar}"] * weight for pillar, weight in moi_weights.items()
    )
    frame["right_to_win_score"] = frame["pillar__right_to_win"]
    frame["rtw_gate"] = _right_to_win_gate(frame["right_to_win_score"], framework)
    frame["cipla_priority_score"] = frame["market_opportunity_index"] * frame["rtw_gate"]

    # Ranks are per level, matching how the scores were normalised.
    for column, rank_name in (
        ("market_opportunity_index", "moi_rank"),
        ("cipla_priority_score", "cps_rank"),
    ):
        frame[rank_name] = (
            frame.groupby("level")[column].rank(ascending=False, method="min").astype(int)
        )

    bands = framework.get_path("scoring.bands", {}) or {}
    high = float(bands.get("high", 70.0))
    medium = float(bands.get("medium", 45.0))
    frame["moi_band"] = np.select(
        [frame["market_opportunity_index"] >= high, frame["market_opportunity_index"] >= medium],
        ["High", "Medium"],
        default="Low",
    )
    frame["rtw_band"] = np.select(
        [frame["right_to_win_score"] >= high, frame["right_to_win_score"] >= medium],
        ["Strong", "Moderate"],
        default="Weak",
    )
    # The strategic verdict falls straight out of the two-axis view. This is the
    # sentence the case asks for: double down, build, be selective, or avoid.
    frame["strategic_verdict"] = np.select(
        [
            (frame["moi_band"] == "High") & (frame["rtw_band"] == "Strong"),
            (frame["moi_band"] == "High") & (frame["rtw_band"] == "Moderate"),
            (frame["moi_band"] == "High") & (frame["rtw_band"] == "Weak"),
            (frame["moi_band"] == "Medium") & (frame["rtw_band"].isin(["Strong", "Moderate"])),
        ],
        [
            "Double down",
            "Build capability",
            "Avoid or partner",
            "Selective participation",
        ],
        default="Harvest or exit",
    )

    all_weights = {"moi_weights": dict(moi_weights), **weights_used}
    logger.info(
        "scorecard.built",
        scored=len(frame),
        excluded=len(excluded),
        levels=sorted(frame["level"].unique().tolist()),
    )
    return ScoreResult(scored=frame, weights=all_weights, excluded=excluded, notes=notes)


def score_from_percentiles(
    percentiles: pd.DataFrame,
    framework: FrameworkConfig,
    weights: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Compute the two headline scores from pre-ranked metrics.

    A stripped-down path for the sensitivity loop, which needs only the scores
    and runs hundreds of times. It performs the same arithmetic as
    :func:`build_scorecard` but skips the frame assembly, banding and verdict
    logic that the loop never reads. Anything that changes the maths here must
    change there too - :func:`~cardiac_agent.analytics.sensitivity.run_sensitivity`
    is only meaningful if both paths agree, and the test suite asserts that.
    """
    gate = framework.get_path("scoring.rtw_gate", {}) or {}
    floor = float(gate.get("floor", 0.35))
    ceiling = float(gate.get("ceiling", 1.0))
    curve = float(gate.get("curve", 1.35))

    pillar_values: dict[str, pd.Series] = {}
    for pillar in PILLARS:
        block = weights.get(pillar) or framework.require(f"scoring.{pillar}")
        total = pd.Series(0.0, index=percentiles.index)
        for metric, weight in block.items():
            total = total + percentiles[f"score__{pillar}__{metric}"] * weight
        pillar_values[pillar] = total

    moi_weights = weights.get("moi_weights") or framework.require("scoring.moi_weights")
    moi = sum(pillar_values[pillar] * weight for pillar, weight in moi_weights.items())
    rtw = pillar_values["right_to_win"]
    gate_values = floor + (ceiling - floor) * ((rtw.clip(0.0, 100.0) / 100.0) ** curve)

    return pd.DataFrame(
        {
            "market_opportunity_index": moi,
            "right_to_win_score": rtw,
            "cipla_priority_score": moi * gate_values,
        },
        index=percentiles.index,
    )


def explain_score(row: pd.Series) -> dict[str, Any]:
    """Break one space's score into its contributing metrics.

    Returned verbatim to the agent so a claim like "it scores well on future
    potential" can be traced to the specific percentile that produced it.
    """
    pillars = {pillar: round(float(row.get(f"pillar__{pillar}", 0.0)), 1) for pillar in PILLARS}
    metrics: dict[str, dict[str, float]] = {}
    for key, value in row.items():
        if not isinstance(key, str) or not key.startswith("score__"):
            continue
        _, pillar, metric = key.split("__", 2)
        metrics.setdefault(pillar, {})[metric] = round(float(value), 1)
    return {
        "market_opportunity_index": round(float(row.get("market_opportunity_index", 0.0)), 1),
        "right_to_win_score": round(float(row.get("right_to_win_score", 0.0)), 1),
        "right_to_win_gate": round(float(row.get("rtw_gate", 0.0)), 3),
        "cipla_priority_score": round(float(row.get("cipla_priority_score", 0.0)), 1),
        "pillars": pillars,
        "metric_percentiles": metrics,
        "strategic_verdict": row.get("strategic_verdict", ""),
    }


__all__ = [
    "INVERTED_METRICS",
    "METRIC_COLUMNS",
    "PILLARS",
    "ScoreResult",
    "build_scorecard",
    "explain_score",
]
