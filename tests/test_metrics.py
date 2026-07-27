"""Growth, demand and competition metric tests.

Expected values are computed by hand in the assertions rather than by calling
the code under test, so a change in the implementation cannot silently redefine
what "real growth" means.
"""

from __future__ import annotations

import pandas as pd
import pytest

from cardiac_agent.analytics.competition import add_competition_metrics
from cardiac_agent.analytics.metrics import add_growth_metrics, market_totals


def _space(**overrides) -> pd.DataFrame:
    base = {
        "level": "sub_segment",
        "space_id": "TEST",
        "space_label": "Test space",
        "segment": "Anti Hypertensives",
        "sub_segment": "ARBs",
        "value_t0": 100.0,
        "value_t1": 120.0,
        "value_t2": 150.0,
        "cp_t0": 100.0,
        "cp_t1": 118.0,
        "cp_t2": 132.0,
        "qty_t0": 1000.0,
        "qty_t1": 1150.0,
        "qty_t2": 1280.0,
        "recent_3m_sales": 40.0,
        "focal_value_t0": 5.0,
        "focal_value_t1": 6.0,
        "focal_value_t2": 9.0,
        "focal_qty_t2": 80.0,
        "sku_count": 10,
    }
    base.update(overrides)
    return pd.DataFrame([base])


class TestGrowthMetrics:
    def test_reported_growth(self):
        out = add_growth_metrics(_space())
        assert out["value_yoy"].iloc[0] == pytest.approx(150.0 / 120.0 - 1.0)

    def test_two_year_cagr(self):
        out = add_growth_metrics(_space())
        assert out["value_cagr_2y"].iloc[0] == pytest.approx((150.0 / 100.0) ** 0.5 - 1.0)

    def test_real_growth_uses_constant_prices_against_prior_reported(self):
        """The glossary defines MAT CP at the prior year's price level.

        Real growth is therefore MAT CP for the latest period against reported
        MAT for the prior period, not against prior-period MAT CP.
        """
        out = add_growth_metrics(_space())
        assert out["real_growth"].iloc[0] == pytest.approx(132.0 / 120.0 - 1.0)

    def test_price_effect_is_the_residual(self):
        out = add_growth_metrics(_space())
        row = out.iloc[0]
        assert row["price_effect"] == pytest.approx(row["value_yoy"] - row["real_growth"])

    def test_price_led_growth_is_visible(self):
        """Value up, constant price flat: the gap must show as price."""
        out = add_growth_metrics(_space(value_t2=150.0, cp_t2=120.0, qty_t2=1150.0))
        row = out.iloc[0]
        assert row["value_yoy"] > 0.2
        assert row["real_growth"] == pytest.approx(0.0)
        assert row["price_effect"] == pytest.approx(row["value_yoy"])

    def test_momentum_annualises_the_three_month_window(self):
        out = add_growth_metrics(_space(recent_3m_sales=45.0, value_t2=150.0))
        # 45 * 4 = 180 annualised against a 150 MAT.
        assert out["momentum"].iloc[0] == pytest.approx(180.0 / 150.0 - 1.0)

    def test_zero_denominators_do_not_explode(self):
        out = add_growth_metrics(
            _space(value_t0=0.0, value_t1=0.0, qty_t1=0.0, cp_t1=0.0, focal_value_t1=0.0)
        )
        row = out.iloc[0]
        for column in ("value_yoy", "value_cagr_2y", "real_growth", "volume_growth", "focal_yoy"):
            assert pd.notna(row[column])
            assert abs(row[column]) < 1e6

    def test_growth_is_clipped(self):
        """A pack going from a rounding artefact to a real number is not a 50,000% opportunity."""
        out = add_growth_metrics(_space(value_t1=0.001, value_t2=100.0))
        assert out["value_yoy"].iloc[0] <= 3.0

    def test_focal_growth_gap_signs_correctly(self):
        out = add_growth_metrics(_space())
        row = out.iloc[0]
        # Cipla 6 -> 9 is +50%; the space 120 -> 150 is +25%. Gap is positive.
        assert row["focal_growth_gap"] > 0


class TestMarketTotals:
    def test_totals_only_use_the_segment_level(self, synthetic_context):
        """Summing any other level would double count."""
        totals = market_totals(synthetic_context["enriched"])
        expected = synthetic_context["skus"]["MAT FEB'26"].sum()
        assert totals["market_value_t2"] == pytest.approx(expected)


class TestCompetitionMetrics:
    def test_hhi_of_a_monopoly_is_ten_thousand(self, synthetic_context):
        spaces = synthetic_context["enriched"]
        # Statins Comb. has a single player in the synthetic market.
        row = spaces[spaces["space_label"].str.contains("Statins Comb.")].iloc[0]
        assert row["hhi"] == pytest.approx(10_000.0)
        assert row["n_players"] == 1
        assert bool(row["is_structurally_closed"])

    def test_hhi_falls_as_players_are_added(self, synthetic_context):
        spaces = synthetic_context["enriched"]
        arbs = spaces[spaces["space_label"].str.contains("ARBs")].iloc[0]
        assert arbs["n_players"] == 2
        assert arbs["hhi"] < 10_000.0

    def test_leader_share_and_company_agree(self, synthetic_context):
        spaces = synthetic_context["enriched"]
        arbs = spaces[spaces["space_label"].str.contains("ARBs")].iloc[0]
        # Torrent 300 against Cipla 100 in the synthetic ARB space.
        assert arbs["leader_company"] == "TORRENT"
        assert arbs["leader_share"] == pytest.approx(0.75)

    def test_price_erosion_is_never_negative(self, synthetic_context):
        assert (synthetic_context["enriched"]["price_erosion"] >= 0).all()

    def test_concentration_labels_follow_thresholds(self):
        frame = _space()
        companies = pd.DataFrame(
            [
                {
                    "level": "sub_segment",
                    "space_id": "TEST",
                    "space_label": "Test space",
                    "company_clean": "A",
                    "value_t1": 50.0,
                    "value_t2": 50.0,
                    "is_mnc": False,
                },
                {
                    "level": "sub_segment",
                    "space_id": "TEST",
                    "space_label": "Test space",
                    "company_clean": "B",
                    "value_t1": 50.0,
                    "value_t2": 50.0,
                    "is_mnc": False,
                },
            ]
        )
        out = add_competition_metrics(add_growth_metrics(frame), companies)
        # Two equal players: HHI = 50^2 + 50^2 = 5000, which is concentrated.
        assert out["hhi"].iloc[0] == pytest.approx(5000.0)
        assert out["concentration_label"].iloc[0] == "Concentrated"
