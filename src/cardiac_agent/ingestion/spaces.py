"""Construct the candidate opportunity spaces.

The case defines an opportunity space loosely - "sub-segments, molecule
classes, molecule combinations, treatment archetypes, or other relevant market
clusters". Rather than pick one, the agent builds all of them and scores them
on a common footing, because the right level of aggregation differs by
question. A portfolio decision is made at sub-segment level; a launch decision
is made at molecule-combination level.

Six levels are produced:

===========================  =============================================
``segment``                  Anti-Hypertensives, Lipid Regulators, Anti-Angina
``sub_segment``              ARBs, Statins Comb., AHT Triple / Poly Comb., ...
``molecule_class``           ATC-4 GROUP, e.g. C02F Hypotensive Dual Comb.
``molecule_combination``     ATC-5 SUBGROUP, e.g. Cilnidipine + Telmisartan
``treatment_archetype``      Monotherapy / Dual FDC / Triple-or-Poly FDC
``anchor_molecule``          Every pack containing a given active ingredient
===========================  =============================================

The anchor-molecule level deliberately overlaps the others: a Cilnidipine +
Telmisartan pack counts towards both the Cilnidipine and the Telmisartan
cluster. That is the point - it exposes molecule franchises that no single
reporting hierarchy shows - and it is why anchor spaces are ranked separately
rather than pooled with the hierarchical levels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from ..logging_config import get_logger

logger = get_logger(__name__)

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")

#: Level identifiers in the order they should be presented.
SPACE_LEVELS: tuple[str, ...] = (
    "segment",
    "sub_segment",
    "molecule_class",
    "molecule_combination",
    "treatment_archetype",
    "anchor_molecule",
)

#: Human-readable description of each level, surfaced by the agent when it
#: explains why a space is defined the way it is.
LEVEL_DESCRIPTIONS: dict[str, str] = {
    "segment": "Therapy segment as classified in the audit (Anti-Hypertensives, Lipid Regulators, Anti-Angina).",
    "sub_segment": "Reported sub-segment: the level at which portfolio and field-force decisions are usually taken.",
    "molecule_class": "ATC-4 molecule class, grouping molecules that share a mechanism and a prescribing occasion.",
    "molecule_combination": "ATC-5 molecule or fixed-dose combination: the level at which a launch decision is made.",
    "treatment_archetype": "Monotherapy versus dual versus triple-or-poly fixed-dose combination, within a segment.",
    "anchor_molecule": "Every pack containing a given active ingredient, whether plain or in combination. Overlaps other levels by design.",
}

#: Values that mean "unclassified" in the source columns.
_PLACEHOLDER_LABELS = {"", "-", "NA", "N/A", "NONE", "NAN"}


def _slug(*parts: str) -> str:
    joined = "__".join(str(part).strip().upper() for part in parts if str(part).strip())
    return _NON_ALNUM.sub("_", joined).strip("_")


@dataclass(frozen=True)
class SpaceDefinition:
    """Identity of one opportunity space, independent of its measures."""

    space_id: str
    level: str
    label: str
    segment: str
    sub_segment: str


def _is_placeholder(value: object) -> bool:
    return str(value).strip().upper() in _PLACEHOLDER_LABELS


def _membership_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Map every SKU row to every space it belongs to.

    Returns a long frame with one row per (SKU, space) pair. Building this once
    means every level is aggregated by the same code, so a bug in the roll-up
    cannot affect one level and not another.
    """
    frame = frame.reset_index(drop=False).rename(columns={"index": "row_id"})
    blocks: list[pd.DataFrame] = []

    def add(
        level: str, label: pd.Series, space_id: pd.Series, mask: pd.Series | None = None
    ) -> None:
        block = pd.DataFrame(
            {
                "row_id": frame["row_id"],
                "level": level,
                "space_label": label.astype(str),
                "space_id": space_id.astype(str),
                "segment": frame["CARDIAC SEGMENT"].astype(str),
                "sub_segment": frame["CARDIAC SUB SEGMENTS"].astype(str),
            }
        )
        if mask is not None:
            block = block[mask.to_numpy()]
        blocks.append(block)

    segment = frame["CARDIAC SEGMENT"].astype(str)
    sub_segment = frame["CARDIAC SUB SEGMENTS"].astype(str)
    group = frame["GROUP"].astype(str)
    subgroup = frame["SUBGROUP"].astype(str)
    archetype = frame["treatment_archetype"].astype(str)

    valid_sub = ~sub_segment.map(_is_placeholder)

    add("segment", segment, segment.map(lambda v: _slug("SEG", v)))
    add(
        "sub_segment",
        segment + " | " + sub_segment,
        (segment + "|" + sub_segment).map(lambda v: _slug("SUB", v)),
        mask=valid_sub,
    )
    add("molecule_class", group, group.map(lambda v: _slug("CLS", v)))
    add(
        "molecule_combination",
        sub_segment + " | " + subgroup,
        subgroup.map(lambda v: _slug("MOL", v)),
        mask=valid_sub,
    )
    add(
        "treatment_archetype",
        segment + " | " + archetype,
        (segment + "|" + archetype).map(lambda v: _slug("ARC", v)),
    )

    # Anchor molecules: one membership row per active ingredient in the pack.
    anchors = frame[["row_id", "molecules", "CARDIAC SEGMENT", "CARDIAC SUB SEGMENTS"]].explode(
        "molecules"
    )
    anchors = anchors[anchors["molecules"].notna() & (anchors["molecules"].astype(str) != "")]
    if not anchors.empty:
        blocks.append(
            pd.DataFrame(
                {
                    "row_id": anchors["row_id"],
                    "level": "anchor_molecule",
                    "space_label": anchors["molecules"].astype(str) + " (all forms)",
                    "space_id": anchors["molecules"].map(lambda v: _slug("ANC", v)),
                    "segment": anchors["CARDIAC SEGMENT"].astype(str),
                    "sub_segment": anchors["CARDIAC SUB SEGMENTS"].astype(str),
                }
            )
        )

    membership = pd.concat(blocks, ignore_index=True)
    logger.info(
        "spaces.membership.built",
        pairs=len(membership),
        levels={level: int(count) for level, count in membership["level"].value_counts().items()},
    )
    return membership


def _aggregate(frame: pd.DataFrame, membership: pd.DataFrame, periods: dict) -> pd.DataFrame:
    """Sum the measures for every space."""
    value = periods["value"]
    constant_price = periods["constant_price"]
    quantity = periods["quantity"]
    monthly = periods["monthly_sales"]

    measure_columns = [
        value["t0"],
        value["t1"],
        value["t2"],
        constant_price["t0"],
        constant_price["t1"],
        constant_price["t2"],
        quantity["t0"],
        quantity["t1"],
        quantity["t2"],
        *monthly,
    ]

    facts = frame.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[["row_id", "is_focal", *measure_columns]],
        on="row_id",
        how="left",
        validate="many_to_one",
    )

    rename = {
        value["t0"]: "value_t0",
        value["t1"]: "value_t1",
        value["t2"]: "value_t2",
        constant_price["t0"]: "cp_t0",
        constant_price["t1"]: "cp_t1",
        constant_price["t2"]: "cp_t2",
        quantity["t0"]: "qty_t0",
        quantity["t1"]: "qty_t1",
        quantity["t2"]: "qty_t2",
    }
    joined = joined.rename(columns=rename)
    joined["recent_3m_sales"] = joined[list(monthly)].sum(axis=1)

    metric_columns = [
        "value_t0",
        "value_t1",
        "value_t2",
        "cp_t0",
        "cp_t1",
        "cp_t2",
        "qty_t0",
        "qty_t1",
        "qty_t2",
        "recent_3m_sales",
    ]

    group_keys = ["level", "space_id", "space_label"]
    totals = joined.groupby(group_keys, as_index=False)[metric_columns].sum()

    focal = (
        joined[joined["is_focal"].fillna(False)]
        .groupby(group_keys, as_index=False)[["value_t0", "value_t1", "value_t2", "qty_t2"]]
        .sum()
        .rename(
            columns={
                "value_t0": "focal_value_t0",
                "value_t1": "focal_value_t1",
                "value_t2": "focal_value_t2",
                "qty_t2": "focal_qty_t2",
            }
        )
    )
    spaces = totals.merge(focal, on=group_keys, how="left")
    for column in ("focal_value_t0", "focal_value_t1", "focal_value_t2", "focal_qty_t2"):
        spaces[column] = spaces[column].fillna(0.0)

    # Attach the dominant segment / sub-segment for readability. A molecule
    # class can straddle two segments; we report the one carrying most value.
    context = (
        joined.groupby([*group_keys, "segment", "sub_segment"], as_index=False)["value_t2"]
        .sum()
        .sort_values("value_t2", ascending=False)
        .drop_duplicates(subset=group_keys)
        .drop(columns=["value_t2"])
    )
    spaces = spaces.merge(context, on=group_keys, how="left")
    spaces["sku_count"] = (
        joined.groupby(group_keys, as_index=False)["row_id"].nunique()["row_id"].to_numpy()
    )
    return spaces


def build_all_spaces(frame: pd.DataFrame, periods: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build every opportunity space and the SKU-to-space membership map.

    Args:
        frame: Normalised Cardiac frame.
        periods: ``market.periods`` block from ``settings.yaml``.

    Returns:
        ``(spaces, membership)``. ``spaces`` carries the summed measures with
        one row per space; ``membership`` retains the SKU-level mapping so
        competitive structure and Cipla's position can be recomputed for any
        subset without re-deriving the hierarchy.
    """
    membership = _membership_frame(frame)
    spaces = _aggregate(frame, membership, periods)
    spaces["level_description"] = spaces["level"].map(LEVEL_DESCRIPTIONS)

    logger.info(
        "spaces.built",
        spaces=len(spaces),
        market_value_t2=float(spaces.loc[spaces["level"] == "segment", "value_t2"].sum()),
    )
    return spaces, membership


__all__ = [
    "LEVEL_DESCRIPTIONS",
    "SPACE_LEVELS",
    "SpaceDefinition",
    "build_all_spaces",
]
