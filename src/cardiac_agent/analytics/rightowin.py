"""Right to win.

The case does not ask which spaces are attractive. It asks which spaces Cipla
has "a clear and sustainable right to win" in. Those are different questions,
and conflating them is how companies end up funding a launch into a market
where the incumbent has a fifteen-year head start.

Right to win is scored on six observable proxies, all derived from the audit
itself rather than asserted:

``current_share``        Where Cipla already stands. A base to defend beats a
                         base to build.
``share_momentum``       Cipla's growth minus the space's growth. Direction
                         matters more than position: 3 per cent share and
                         gaining beats 8 per cent and bleeding.
``molecule_adjacency``   Does Cipla already manufacture and sell the active
                         ingredients this space is built on? If yes, the
                         formulation, the regulatory file and the API sourcing
                         already exist.
``brand_franchise``      Is there an umbrella brand to extend? Launching
                         Rosulip-EZ into rosuvastatin-plus-ezetimibe borrows
                         a decade of prescriber recall. An unbranded entrant
                         starts from nothing.
``detailing_adjacency``  Is the field force already in front of these
                         prescribers? Sub-segment presence is the proxy.
``formulation_fit``      How closely the space's dosage-form mix matches what
                         Cipla already makes in cardiac.

Each is bounded to [0, 1] here; the weighted blend happens in ``scoring``.
"""

from __future__ import annotations

import pandas as pd

from ..logging_config import get_logger
from .metrics import EPSILON

logger = get_logger(__name__)


class FocalProfile:
    """Everything the scorer needs to know about the focal company's estate.

    Computed once from the SKU table, then reused for every space, so a
    scorecard over six levels does not rescan the fact table six times.
    """

    def __init__(self, sku_facts: pd.DataFrame, value_column: str) -> None:
        focal = sku_facts[sku_facts["is_focal"]]
        self.value_column = value_column
        self.present = not focal.empty

        active = focal[focal[value_column] > EPSILON]

        # Molecules the company already markets, in any pack, plain or combined.
        self.molecules: set[str] = {
            molecule
            for signature in active["molecule_canonical"].astype(str)
            for molecule in (part.strip() for part in signature.split("+"))
            if molecule
        }
        self.subgroups: set[str] = set(active["SUBGROUP"].astype(str))
        self.sub_segments: set[str] = set(active["CARDIAC SUB SEGMENTS"].astype(str))
        self.segments: set[str] = set(active["CARDIAC SEGMENT"].astype(str))

        # Umbrella brand roots, and the molecules each already carries.
        self.brand_roots: set[str] = set(active["brand_root"].astype(str)) - {""}
        self.brand_molecules: dict[str, set[str]] = {}
        for _, row in active.iterrows():
            root = str(row["brand_root"])
            if not root:
                continue
            bucket = self.brand_molecules.setdefault(root, set())
            bucket.update(
                part.strip()
                for part in str(row["molecule_canonical"]).split("+")
                if part.strip()
            )

        # Molecules covered by at least one existing umbrella brand.
        self.branded_molecules: set[str] = {
            molecule for molecules in self.brand_molecules.values() for molecule in molecules
        }

        # Dosage-form mix, used as the capability vector for formulation fit.
        total = float(active[value_column].sum())
        if total > EPSILON:
            solids = float(active.loc[active["is_oral_solid"], value_column].sum())
            self.solids_share = solids / total
        else:
            self.solids_share = 1.0

        logger.info(
            "focal_profile.built",
            present=self.present,
            molecules=len(self.molecules),
            brand_roots=len(self.brand_roots),
            solids_share=round(self.solids_share, 4),
        )


def _space_composition(
    sku_facts: pd.DataFrame, membership: pd.DataFrame, value_column: str
) -> pd.DataFrame:
    """Value-weighted composition of every space: molecules, forms, sub-segments."""
    facts = sku_facts.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[
            [
                "row_id",
                "molecule_canonical",
                "SUBGROUP",
                "CARDIAC SUB SEGMENTS",
                "CARDIAC SEGMENT",
                "is_oral_solid",
                value_column,
            ]
        ],
        on="row_id",
        how="left",
        validate="many_to_one",
    ).rename(columns={value_column: "value"})

    joined["value"] = joined["value"].fillna(0.0).astype(float)

    records: list[dict] = []
    for (level, space_id), group in joined.groupby(["level", "space_id"], sort=False):
        total = float(group["value"].sum())
        if total <= EPSILON:
            records.append(
                {
                    "level": level,
                    "space_id": space_id,
                    "molecule_weights": {},
                    "subgroups": set(),
                    "sub_segments": set(),
                    "segments": set(),
                    "solids_share": 1.0,
                }
            )
            continue

        molecule_weights: dict[str, float] = {}
        for signature, value in zip(
            group["molecule_canonical"].astype(str), group["value"], strict=False
        ):
            parts = [part.strip() for part in signature.split("+") if part.strip()]
            if not parts:
                continue
            # Split a combination pack's value evenly across its ingredients so
            # a triple FDC does not count three times over.
            per_molecule = float(value) / len(parts)
            for part in parts:
                molecule_weights[part] = molecule_weights.get(part, 0.0) + per_molecule

        records.append(
            {
                "level": level,
                "space_id": space_id,
                "molecule_weights": {k: v / total for k, v in molecule_weights.items()},
                "subgroups": set(group["SUBGROUP"].astype(str)),
                "sub_segments": set(group["CARDIAC SUB SEGMENTS"].astype(str)),
                "segments": set(group["CARDIAC SEGMENT"].astype(str)),
                "solids_share": float(group.loc[group["is_oral_solid"] == True, "value"].sum())  # noqa: E712
                / total,
            }
        )
    return pd.DataFrame.from_records(records)


def add_right_to_win_metrics(
    spaces: pd.DataFrame,
    sku_facts: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    value_column: str = "MAT FEB'26",
) -> pd.DataFrame:
    """Attach the six right-to-win components to the space frame.

    Args:
        spaces: Space frame carrying growth metrics.
        sku_facts: SKU-level table from the warehouse.
        membership: SKU-to-space map from the warehouse.
        value_column: Latest-period value column in ``sku_facts``.

    Returns:
        A copy of ``spaces`` with the right-to-win components appended, each in
        the range [0, 1] except ``rtw_share_momentum`` which is a signed growth
        gap and is normalised later.
    """
    profile = FocalProfile(sku_facts, value_column)
    composition = _space_composition(sku_facts, membership, value_column)
    out = spaces.merge(composition, on=["level", "space_id"], how="left")

    # Cipla's share of each sub-segment, the proxy for prescriber coverage.
    sub_segment_share: dict[str, float] = {}
    sub_rows = spaces[spaces["level"] == "sub_segment"]
    for _, row in sub_rows.iterrows():
        label = str(row.get("sub_segment", "")).strip()
        total = float(row["value_t2"])
        if label and total > EPSILON:
            sub_segment_share[label] = float(row["focal_value_t2"]) / total

    molecule_adjacency: list[float] = []
    brand_franchise: list[float] = []
    detailing: list[float] = []
    formulation: list[float] = []
    adjacent_brands: list[str] = []

    for _, row in out.iterrows():
        weights: dict[str, float] = row.get("molecule_weights") or {}
        subgroups: set[str] = row.get("subgroups") or set()
        sub_segments: set[str] = row.get("sub_segments") or set()
        segments: set[str] = row.get("segments") or set()

        # --- Molecule adjacency: value-weighted overlap with Cipla's estate.
        molecule_adjacency.append(
            sum(weight for molecule, weight in weights.items() if molecule in profile.molecules)
            if weights
            else 0.0
        )

        # --- Brand franchise: strongest available extension route.
        matching_brands = sorted(
            {
                root
                for root, molecules in profile.brand_molecules.items()
                if molecules & set(weights)
            }
        )
        if matching_brands:
            score = 1.0
        elif profile.subgroups & subgroups:
            score = 0.75
        elif profile.sub_segments & sub_segments:
            score = 0.60
        elif profile.segments & segments:
            score = 0.30
        else:
            score = 0.0
        brand_franchise.append(score)
        adjacent_brands.append(", ".join(matching_brands[:4]))

        # --- Detailing adjacency: presence with the same prescriber pool.
        shares = [sub_segment_share.get(label, 0.0) for label in sub_segments if label]
        detailing.append(max(shares) if shares else 0.0)

        # --- Formulation fit: overlap of dosage-form mix with Cipla's.
        space_solids = float(row.get("solids_share") or 0.0)
        formulation.append(
            space_solids * profile.solids_share
            + (1.0 - space_solids) * (1.0 - profile.solids_share)
        )

    out["rtw_molecule_adjacency"] = molecule_adjacency
    out["rtw_brand_franchise"] = brand_franchise
    out["rtw_detailing_adjacency"] = detailing
    out["rtw_formulation_fit"] = formulation
    out["rtw_current_share"] = out["focal_share_t2"].astype(float)
    out["rtw_share_momentum"] = out["focal_growth_gap"].astype(float).clip(-0.5, 0.5)
    out["adjacent_cipla_brands"] = adjacent_brands

    # Drop the intermediate object columns: DuckDB cannot store Python sets and
    # they are not needed downstream.
    out = out.drop(columns=["molecule_weights", "subgroups", "sub_segments", "segments"])
    out = out.rename(columns={"solids_share": "space_solids_share"})

    return out


__all__ = ["FocalProfile", "add_right_to_win_metrics"]
