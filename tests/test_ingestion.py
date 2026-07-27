"""Ingestion and derivation tests."""

from __future__ import annotations

import pandas as pd
import pytest

from cardiac_agent.ingestion.normalize import brand_root, normalize_cardiac_frame, split_molecules
from cardiac_agent.ingestion.spaces import build_all_spaces


class TestMoleculeSplitting:
    def test_splits_a_combination(self):
        assert split_molecules("AMLODIPINE BESILATE + ATENOLOL") == ["AMLODIPINE", "ATENOLOL"]

    def test_strips_salt_suffixes(self):
        assert split_molecules("METOPROLOL SUCCINATE") == ["METOPROLOL"]
        assert split_molecules("OLMESARTAN MEDOXOMIL") == ["OLMESARTAN"]

    def test_strips_stacked_qualifiers(self):
        # "ROSUVASTATIN CALCIUM SALT" needs two passes to reduce.
        assert split_molecules("ROSUVASTATIN CALCIUM SALT") == ["ROSUVASTATIN"]

    def test_keeps_nitrate_esters_distinct(self):
        # Mononitrate and dinitrate are different drugs, not salt forms of one.
        assert split_molecules("ISOSORBIDE MONONITRATE") == ["ISOSORBIDE MONONITRATE"]
        assert split_molecules("ISOSORBIDE DINITRATE") == ["ISOSORBIDE DINITRATE"]

    def test_deduplicates_and_handles_blanks(self):
        assert split_molecules("ATENOLOL + ATENOLOL") == ["ATENOLOL"]
        assert split_molecules("") == []
        assert split_molecules(None) == []


class TestBrandRoot:
    @pytest.mark.parametrize(
        ("brand", "expected"),
        [
            ("AMLOPRES-AT", "AMLOPRES"),
            ("ROSULIP GOLD", "ROSULIP"),
            ("CRESAR AMH", "CRESAR"),
            ("AMLIP AT", "AMLIP"),
            ("TELMA-H", "TELMA"),
            ("ECOSPRIN-AV", "ECOSPRIN"),
        ],
    )
    def test_recovers_umbrella_brand(self, brand, expected):
        assert brand_root(brand) == expected

    def test_leaves_two_word_brands_intact(self):
        # REVELOL is a brand, not a line-extension modifier.
        assert brand_root("ACE REVELOL") == "ACE REVELOL"

    def test_handles_short_and_empty_names(self):
        assert brand_root("5-MONO") == "5-MONO"
        assert brand_root("") == ""


class TestNormalisation:
    def test_flags_the_focal_company(self, synthetic_skus):
        out = normalize_cardiac_frame(synthetic_skus, focal_company="CIPLA*")
        assert out["is_focal"].sum() == 2
        assert set(out.loc[out["is_focal"], "BRANDS"]) == {"BRAND-A", "BRAND-D"}

    def test_strips_the_consolidation_marker(self, synthetic_skus):
        out = normalize_cardiac_frame(synthetic_skus)
        assert "CIPLA" in set(out["company_clean"])
        assert not any("*" in value for value in out["company_clean"])

    def test_classifies_treatment_archetype(self, synthetic_skus):
        out = normalize_cardiac_frame(synthetic_skus)
        archetypes = dict(zip(out["BRANDS"], out["treatment_archetype"], strict=False))
        assert archetypes["BRAND-A"] == "Monotherapy"
        assert archetypes["BRAND-C"] == "Dual FDC"

    def test_does_not_mutate_the_input(self, synthetic_skus):
        before = synthetic_skus.copy()
        normalize_cardiac_frame(synthetic_skus)
        pd.testing.assert_frame_equal(synthetic_skus, before)


class TestSpaceConstruction:
    def test_builds_every_level(self, synthetic_skus, framework):
        out = normalize_cardiac_frame(synthetic_skus)
        spaces, _ = build_all_spaces(out, framework.require("market.periods"))
        assert set(spaces["level"]) == {
            "segment",
            "sub_segment",
            "molecule_class",
            "molecule_combination",
            "treatment_archetype",
            "anchor_molecule",
        }

    def test_segment_totals_reconcile_with_the_source(self, synthetic_skus, framework):
        out = normalize_cardiac_frame(synthetic_skus)
        spaces, _ = build_all_spaces(out, framework.require("market.periods"))
        segment_total = spaces.loc[spaces["level"] == "segment", "value_t2"].sum()
        assert segment_total == pytest.approx(out["MAT FEB'26"].sum())

    def test_anchor_level_overlaps_by_design(self, synthetic_skus, framework):
        """A combination pack counts towards every molecule it contains.

        This is intended, and it is why anchor spaces are ranked separately
        rather than pooled with the hierarchical levels.
        """
        out = normalize_cardiac_frame(synthetic_skus)
        spaces, _ = build_all_spaces(out, framework.require("market.periods"))
        anchors = spaces[spaces["level"] == "anchor_molecule"]
        assert anchors["value_t2"].sum() > out["MAT FEB'26"].sum()

    def test_telmisartan_anchor_spans_plain_and_combination(self, synthetic_skus, framework):
        out = normalize_cardiac_frame(synthetic_skus)
        spaces, _ = build_all_spaces(out, framework.require("market.periods"))
        telmisartan = spaces[
            (spaces["level"] == "anchor_molecule")
            & (spaces["space_label"].str.startswith("TELMISARTAN"))
        ]
        assert len(telmisartan) == 1
        # BRAND-A + BRAND-B (plain) + BRAND-C (combination) = 100 + 300 + 250
        assert float(telmisartan["value_t2"].iloc[0]) == pytest.approx(650.0)


@pytest.mark.requires_data
class TestRealWorkbook:
    def test_market_total_reconciles(self, real_context):
        segments = real_context.enriched[real_context.enriched["level"] == "segment"]
        assert segments["value_t2"].sum() == pytest.approx(
            real_context.totals["market_value_t2"], rel=1e-9
        )

    def test_focal_company_is_present(self, real_context):
        assert real_context.totals["focal_value_t2"] > 0
        assert 0 < real_context.totals["focal_share"] < 0.5

    def test_build_metadata_records_provenance(self, real_context):
        assert len(real_context.metadata["source_sha256"]) == 64
        assert real_context.metadata["sku_rows"] > 1000
