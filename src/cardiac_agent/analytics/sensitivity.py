"""Weight sensitivity.

Any scoring framework can be accused of engineering its own conclusion: pick
the weights, get the answer you wanted. The honest response is to show what
happens when the weights move.

The analysis re-draws every weight block from a Dirichlet distribution centred
on the configured values, re-scores the market several hundred times, and
reports how often each space stays in the top K. A recommendation that survives
90 per cent of plausible weightings is robust. One that appears in 40 per cent
is a judgement call, and the agent is required to say so out loud.

This is the module that matters most in a live challenge. When a panel asks
"what if you cared less about size and more about growth", the answer is a
number, not an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..config import FrameworkConfig, get_framework
from ..logging_config import get_logger
from .scoring import PILLARS, build_scorecard, metric_percentiles, score_from_percentiles

logger = get_logger(__name__)


@dataclass
class SensitivityResult:
    """Rank stability across randomised weightings."""

    stability: pd.DataFrame
    iterations: int
    top_k: int
    concentration: float
    baseline_top: list[str]

    def summary(self, limit: int = 10) -> list[dict[str, Any]]:
        """Compact view for the agent's evidence pack."""
        return self.stability.head(limit)[
            [
                "space_id",
                "space_label",
                "level",
                "baseline_rank",
                "top_k_frequency",
                "mean_rank",
                "worst_rank",
            ]
        ].to_dict(orient="records")


def _perturb(
    weights: dict[str, float], concentration: float, rng: np.random.Generator
) -> dict[str, float]:
    """Draw a weight block from a Dirichlet centred on the configured values."""
    keys = list(weights)
    alpha = np.array([max(weights[k], 1e-6) * concentration for k in keys], dtype=float)
    drawn = rng.dirichlet(alpha)
    return dict(zip(keys, (float(v) for v in drawn), strict=False))


def run_sensitivity(
    spaces: pd.DataFrame,
    *,
    level: str = "molecule_combination",
    framework: FrameworkConfig | None = None,
    iterations: int | None = None,
    top_k: int | None = None,
    min_value_cr: float | None = None,
    min_players: int | None = None,
    score_column: str = "cipla_priority_score",
) -> SensitivityResult:
    """Re-score the market under randomised weights and measure rank stability.

    Args:
        spaces: Space frame with all metrics attached (pre-scoring).
        level: Which space level to test. Ranking is per level anyway.
        framework: Parsed configuration.
        iterations: Number of random weightings. Defaults to config.
        top_k: Size of the "top" set whose membership is tracked.
        min_value_cr: Override the size floor applied before scoring.
        min_players: Override the minimum active-competitor filter.
        score_column: Which score to rank on.

    Returns:
        A :class:`SensitivityResult` ordered by how often each space appears in
        the top K.
    """
    framework = framework or get_framework()
    iterations = int(iterations or framework.get_path("sensitivity.iterations", 500))
    top_k = int(top_k or framework.get_path("sensitivity.top_k", 5))
    concentration = float(framework.get_path("sensitivity.concentration", 40.0))
    seed = int(framework.get_path("sensitivity.random_seed", 20260808))
    rng = np.random.default_rng(seed)

    baseline = build_scorecard(
        spaces,
        framework=framework,
        levels=[level],
        min_value_cr=min_value_cr,
        min_players=min_players,
    )

    # Percentile ranking does not depend on the weights, so it is computed once
    # against exactly the rows that survived the baseline's filters and reused
    # for every iteration. Without this the loop re-ranks the market hundreds of
    # times and the analysis takes a minute instead of under a second.
    survivors = spaces.loc[baseline.scored.index]
    percentiles = metric_percentiles(survivors, framework)

    baseline_frame = baseline.scored.sort_values(score_column, ascending=False)
    baseline_top = baseline_frame.head(top_k)["space_id"].tolist()
    baseline_ranks = {
        row["space_id"]: int(index + 1) for index, (_, row) in enumerate(baseline_frame.iterrows())
    }

    appearances: dict[str, int] = dict.fromkeys(baseline_ranks, 0)
    rank_samples: dict[str, list[int]] = {space: [] for space in baseline_ranks}

    base_moi = dict(framework.require("scoring.moi_weights"))
    base_pillars = {pillar: dict(framework.require(f"scoring.{pillar}")) for pillar in PILLARS}

    space_ids = survivors["space_id"].astype(str)

    for _ in range(iterations):
        overrides: dict[str, dict[str, float]] = {
            "moi_weights": _perturb(base_moi, concentration, rng)
        }
        for pillar, block in base_pillars.items():
            overrides[pillar] = _perturb(block, concentration, rng)

        scores = score_from_percentiles(percentiles, framework, overrides)
        ordered = space_ids.loc[scores[score_column].sort_values(ascending=False).index]
        top_ids = set(ordered.head(top_k))
        for position, space_id in enumerate(ordered, start=1):
            if space_id in rank_samples:
                rank_samples[space_id].append(position)
            if space_id in appearances and space_id in top_ids:
                appearances[space_id] += 1

    records = []
    for space_id, base_rank in baseline_ranks.items():
        samples = rank_samples[space_id] or [base_rank]
        label = baseline_frame.loc[baseline_frame["space_id"] == space_id, "space_label"]
        records.append(
            {
                "space_id": space_id,
                "space_label": label.iloc[0] if len(label) else space_id,
                "level": level,
                "baseline_rank": base_rank,
                "top_k_frequency": round(appearances[space_id] / iterations, 4),
                "mean_rank": round(float(np.mean(samples)), 2),
                "median_rank": float(np.median(samples)),
                "worst_rank": int(np.max(samples)),
                "best_rank": int(np.min(samples)),
            }
        )

    stability = pd.DataFrame.from_records(records).sort_values(
        ["top_k_frequency", "mean_rank"], ascending=[False, True]
    )

    logger.info(
        "sensitivity.done",
        level=level,
        iterations=iterations,
        top_k=top_k,
        robust_spaces=int((stability["top_k_frequency"] >= 0.8).sum()),
    )
    return SensitivityResult(
        stability=stability,
        iterations=iterations,
        top_k=top_k,
        concentration=concentration,
        baseline_top=baseline_top,
    )


__all__ = ["SensitivityResult", "run_sensitivity"]
