"""Deterministic analytics.

Every number the agent reports is produced here, in ordinary Python, from the
warehouse. The language model never computes, estimates or interpolates a
figure - it receives a finished evidence pack and writes prose about it. That
separation is what makes the output auditable: re-running this package on the
same workbook reproduces the same scorecard, byte for byte.
"""

from .competition import add_competition_metrics
from .forecast import forecast_space, forecast_spaces
from .metrics import add_growth_metrics
from .rightowin import add_right_to_win_metrics
from .scoring import ScoreResult, build_scorecard
from .sensitivity import run_sensitivity
from .whitespace import find_whitespace

__all__ = [
    "ScoreResult",
    "add_competition_metrics",
    "add_growth_metrics",
    "add_right_to_win_metrics",
    "build_scorecard",
    "find_whitespace",
    "forecast_space",
    "forecast_spaces",
    "run_sensitivity",
]
