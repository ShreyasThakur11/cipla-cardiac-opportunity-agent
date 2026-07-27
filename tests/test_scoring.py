"""Scoring, forecasting and sensitivity tests."""

from __future__ import annotations

import numpy as np
import pytest

from cardiac_agent.analytics.forecast import forecast_space
from cardiac_agent.analytics.scoring import (
    PILLARS,
    build_scorecard,
    explain_score,
    metric_percentiles,
    score_from_percentiles,
)
from cardiac_agent.analytics.sensitivity import run_sensitivity
from cardiac_agent.analytics.whitespace import WhitespaceCriteria, find_whitespace


class TestConfiguredWeights:
    def test_every_weight_block_sums_to_one(self, framework):
        for block in ["moi_weights", *PILLARS]:
            weights = framework.require(f"scoring.{block}")
            assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6), (
                f"scoring.{block} must sum to 1.0"
            )

    def test_rejects_weights_that_do_not_sum_to_one(self, synthetic_context, framework):
        with pytest.raises(ValueError, match="expected 1.0"):
            build_scorecard(
                synthetic_context["enriched"],
                framework=framework,
                weight_overrides={"future_potential": {"real_growth": 0.5, "volume_growth": 0.2}},
                min_value_cr=0.0,
            )


class TestScorecard:
    def test_scores_are_bounded(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        for column in ("market_opportunity_index", "right_to_win_score", "cipla_priority_score"):
            assert result.scored[column].between(0.0, 100.0).all()

    def test_priority_never_exceeds_opportunity(self, synthetic_context, framework):
        """The right-to-win gate is a multiplier bounded at 1.0, so it can only reduce."""
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        assert (
            result.scored["cipla_priority_score"]
            <= result.scored["market_opportunity_index"] + 1e-9
        ).all()

    def test_the_gate_punishes_weak_right_to_win(self, framework):
        gate = framework.get_path("scoring.rtw_gate")
        floor, ceiling, curve = gate["floor"], gate["ceiling"], gate["curve"]
        weak = floor + (ceiling - floor) * (0.2**curve)
        strong = floor + (ceiling - floor) * (0.8**curve)
        assert weak < strong
        # A curve above 1.0 must bend below the linear interpolation.
        assert weak < floor + (ceiling - floor) * 0.2

    def test_size_filter_excludes_and_explains(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=200.0
        )
        assert (result.scored["value_t2"] >= 200.0).all()
        if not result.excluded.empty:
            assert result.excluded["exclusion_reason"].notna().all()

    def test_ranks_are_per_level(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        for _, group in result.scored.groupby("level"):
            assert group["cps_rank"].min() == 1

    def test_verdicts_come_from_the_two_axis_view(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        allowed = {
            "Double down",
            "Build capability",
            "Avoid or partner",
            "Selective participation",
            "Harvest or exit",
        }
        assert set(result.scored["strategic_verdict"]) <= allowed

    def test_explain_score_exposes_the_components(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        explanation = explain_score(result.scored.iloc[0])
        assert set(explanation["pillars"]) == set(PILLARS)
        assert explanation["metric_percentiles"]


class TestLeanScoringPath:
    def test_matches_the_full_path_exactly(self, synthetic_context, framework):
        """The sensitivity loop's shortcut must not change the answer.

        If these ever diverge, every stability number reported to a jury would
        be measuring a different framework from the one being presented.
        """
        spaces = synthetic_context["enriched"]
        full = build_scorecard(spaces, framework=framework, min_value_cr=0.0)
        survivors = spaces.loc[full.scored.index]
        percentiles = metric_percentiles(survivors, framework)
        lean = score_from_percentiles(percentiles, framework, full.weights)

        for column in ("market_opportunity_index", "right_to_win_score", "cipla_priority_score"):
            np.testing.assert_allclose(
                lean[column].to_numpy(), full.scored[column].to_numpy(), rtol=1e-12, atol=1e-12
            )


class TestForecast:
    def test_mean_reverts_towards_the_market(self, synthetic_context, framework):
        spaces = synthetic_context["enriched"]
        fast = spaces.sort_values("real_growth", ascending=False).iloc[0]
        forecast = forecast_space(fast, market_cagr=0.12, framework=framework, horizon_years=5)
        # The effective CAGR must sit below the starting rate because the
        # excess over the market decays each year.
        assert forecast.base_cagr < max(fast["real_growth"], fast["volume_growth"])

    def test_scenarios_bracket_the_base_case(self, synthetic_context, framework):
        row = synthetic_context["enriched"].iloc[0]
        forecast = forecast_space(row, market_cagr=0.12, framework=framework)
        assert forecast.bear_value_cr <= forecast.projected_value_cr <= forecast.bull_value_cr

    def test_rate_is_capped(self, synthetic_context, framework):
        cap = float(framework.get_path("forecast.max_projected_cagr"))
        row = synthetic_context["enriched"].sort_values("real_growth", ascending=False).iloc[0]
        forecast = forecast_space(row, market_cagr=0.12, framework=framework)
        assert forecast.base_cagr <= cap + 1e-9

    def test_assumptions_are_reported(self, synthetic_context, framework):
        row = synthetic_context["enriched"].iloc[0]
        forecast = forecast_space(row, market_cagr=0.12, framework=framework)
        assert len(forecast.assumptions) >= 4


class TestSensitivity:
    def test_is_reproducible(self, synthetic_context, framework):
        """Same seed, same answer. A stability number that moves per run is noise."""
        first = run_sensitivity(
            synthetic_context["enriched"],
            level="sub_segment",
            framework=framework,
            iterations=60,
            min_value_cr=0.0,
            min_players=1,
        )
        second = run_sensitivity(
            synthetic_context["enriched"],
            level="sub_segment",
            framework=framework,
            iterations=60,
            min_value_cr=0.0,
            min_players=1,
        )
        assert first.stability["top_k_frequency"].tolist() == (
            second.stability["top_k_frequency"].tolist()
        )

    def test_frequencies_are_probabilities(self, synthetic_context, framework):
        result = run_sensitivity(
            synthetic_context["enriched"],
            level="sub_segment",
            framework=framework,
            iterations=60,
            min_value_cr=0.0,
            min_players=1,
        )
        assert result.stability["top_k_frequency"].between(0.0, 1.0).all()


class TestWhitespace:
    def test_requires_a_route_in(self, synthetic_context, framework):
        """A space with no molecule and no brand adjacency is not whitespace."""
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        criteria = WhitespaceCriteria(min_moi=0.0, min_value_cr=0.0)
        found = find_whitespace(result.scored, focal_overall_share=0.05, criteria=criteria)
        if not found.empty:
            assert (found["route_to_win"] != "no obvious route in").all()

    def test_value_gap_is_the_prize(self, synthetic_context, framework):
        result = build_scorecard(
            synthetic_context["enriched"], framework=framework, min_value_cr=0.0
        )
        criteria = WhitespaceCriteria(min_moi=0.0, min_value_cr=0.0)
        found = find_whitespace(result.scored, focal_overall_share=0.05, criteria=criteria)
        if not found.empty:
            row = found.iloc[0]
            assert row["value_gap_cr"] == pytest.approx(
                row["value_t2"] * 0.05 - row["focal_value_t2"], rel=1e-6
            )
