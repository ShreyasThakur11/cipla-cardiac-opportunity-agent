"""Derive the fields the analysis needs but the workbook does not supply.

Four derivations matter downstream, and each answers a specific question the
case asks:

``molecules`` / ``anchor_molecules``
    "molecule classes and molecule combinations" - splitting the combination
    string lets us see that Cilnidipine appears in a plain CCB, three dual
    combinations and two triples, and add those up as one franchise.

``treatment_archetype``
    "treatment archetypes" - monotherapy, dual fixed-dose combination,
    triple-or-more. This is the axis prescriber behaviour actually moves along.

``brand_root``
    Whether Cipla can extend an existing brand into a space. Launching
    Rosulip-EZ into rosuvastatin-plus-ezetimibe is a different proposition from
    launching an unbranded entrant, and the scorecard should say so.

``company_clean``
    The audit marks consolidated corporate groups with a trailing asterisk
    (``CIPLA*``, ``SUN*``). Removing it gives readable output while the raw
    value stays available for exact joins.
"""

from __future__ import annotations

import re

import pandas as pd

from ..logging_config import get_logger

logger = get_logger(__name__)

#: Salt and ester suffixes that name a formulation, not a distinct active
#: ingredient. Stripping them lets "AMLODIPINE BESILATE" and "AMLODIPINE" roll
#: into one franchise. Deliberately conservative: nitrate esters are NOT here,
#: because isosorbide mononitrate and dinitrate are genuinely different drugs.
SALT_SUFFIXES: tuple[str, ...] = (
    "BESILATE",
    "BESYLATE",
    "SUCCINATE",
    "TARTRATE",
    "MALEATE",
    "FUMARATE",
    "HYDROCHLORIDE",
    "MESYLATE",
    "MEDOXOMIL",
    "CILEXETIL",
    "ARGININE",
    "HEMIHYDRATE",
    "DIHYDRATE",
    "MONOHYDRATE",
    "MAGNESIUM",
    "POTASSIUM",
    "CALCIUM",
    "SODIUM",
    "HCL",
    # "SALT" appears as a trailing qualifier, e.g. "ROSUVASTATIN CALCIUM SALT".
    # Listing it lets the loop strip SALT and then CALCIUM in turn.
    "SALT",
)

#: Short tokens that follow an umbrella brand to denote a line extension:
#: Rosulip GOLD, Amlopres TRIO, Cresar AMH. Used to recover the umbrella name.
BRAND_MODIFIER_TOKENS: frozenset[str] = frozenset(
    {
        "GOLD", "TRIO", "PLUS", "FORTE", "XL", "SR", "CR", "OD", "CV", "ASP",
        "AM", "AT", "H", "CT", "D", "M", "F", "EZ", "LN", "BS", "3D", "TL",
        "L", "B", "A", "T", "S", "MF", "AH", "HT", "DS",
    }
)

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _canonical_molecule(token: str) -> str:
    """Reduce one molecule token to its active-ingredient name."""
    cleaned = token.strip().upper()
    if not cleaned:
        return ""
    words = cleaned.split()
    # Strip trailing salt words, e.g. "AMLODIPINE BESILATE" -> "AMLODIPINE".
    while len(words) > 1 and words[-1] in SALT_SUFFIXES:
        words.pop()
    return " ".join(words)


def split_molecules(description: str) -> list[str]:
    """Split a MOLECULE_DESC string into canonical active ingredients.

    >>> split_molecules("AMLODIPINE BESILATE + ATENOLOL")
    ['AMLODIPINE', 'ATENOLOL']
    """
    if not isinstance(description, str) or not description.strip():
        return []
    parts = [_canonical_molecule(part) for part in description.split("+")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return seen


def brand_root(brand: str) -> str:
    """Recover the umbrella brand from a line-extension name.

    ``AMLOPRES-AT`` and ``AMLOPRES TRIO`` both belong to the ``AMLOPRES``
    franchise. ``ACE REVELOL`` does not decompose - ``REVELOL`` is not a
    modifier - so the full name is kept.
    """
    if not isinstance(brand, str) or not brand.strip():
        return ""
    text = brand.strip().upper()

    # A hyphen is an unambiguous extension marker.
    if "-" in text:
        head = text.split("-", 1)[0].strip()
        if len(head) >= 3:
            return head

    tokens = text.split()
    if len(tokens) > 1 and len(tokens[0]) >= 3:
        tail = tokens[1:]
        looks_like_extension = all(
            token in BRAND_MODIFIER_TOKENS or len(token) <= 3 for token in tail
        )
        if looks_like_extension:
            return tokens[0]
    return text


def _treatment_archetype(plain_combination: str, molecule_count: int) -> str:
    """Classify a pack by how many active ingredients the prescriber is buying."""
    label = (plain_combination or "").strip().lower()
    if label.startswith("plain") or molecule_count <= 1:
        return "Monotherapy"
    if molecule_count == 2:
        return "Dual FDC"
    return "Triple / Poly FDC"


def _slug(value: str) -> str:
    """Filesystem- and URL-safe identifier fragment."""
    return _NON_ALNUM.sub("_", str(value).strip().upper()).strip("_")


def normalize_cardiac_frame(frame: pd.DataFrame, focal_company: str = "CIPLA*") -> pd.DataFrame:
    """Add derived columns to the validated Cardiac frame.

    Args:
        frame: Output of :func:`~.excel_loader.load_cardiac_workbook`.
        focal_company: Raw COMPANY value identifying the focal player.

    Returns:
        A copy of ``frame`` with derived columns appended. The input is never
        mutated, so a caller can keep the raw frame for reconciliation.
    """
    out = frame.copy()

    out["company_clean"] = out["COMPANY"].astype(str).str.replace("*", "", regex=False).str.strip()
    out["is_focal"] = out["COMPANY"].astype(str).str.strip() == focal_company

    molecules = out["MOLECULE_DESC"].map(split_molecules)
    out["molecules"] = molecules
    out["molecule_count"] = molecules.map(len)
    out["molecule_canonical"] = molecules.map(lambda parts: " + ".join(parts))
    # Sorted form so "A + B" and "B + A" describe the same combination.
    out["molecule_signature"] = molecules.map(lambda parts: " + ".join(sorted(parts)))

    out["treatment_archetype"] = [
        _treatment_archetype(pc, count)
        for pc, count in zip(out["Plain/Combination"], out["molecule_count"], strict=False)
    ]

    out["brand_root"] = out["BRANDS"].map(brand_root)
    out["brand_key"] = out["company_clean"].str.upper() + " | " + out["brand_root"]

    # Realised price per unit. QTY can legitimately be zero for a pack that had
    # value but no recorded units, so guard the division rather than dropping it.
    quantity = out["QTY MAT FEB'26"].astype(float)
    realised = out["MAT FEB'26"].astype(float).divide(quantity.where(quantity != 0.0))
    out["realised_price_per_unit"] = (
        realised.replace([float("inf"), float("-inf")], pd.NA).fillna(0.0).astype(float)
    )

    out["is_oral_solid"] = out["FINAL NFC"].astype(str).str.upper().eq("SOLIDS")
    out["is_mnc"] = out["INDIAN_MNC"].astype(str).str.upper().eq("MNC")

    out["segment_slug"] = out["CARDIAC SEGMENT"].map(_slug)
    out["sub_segment_slug"] = out["CARDIAC SUB SEGMENTS"].map(_slug)
    out["subgroup_slug"] = out["SUBGROUP"].map(_slug)

    focal_rows = int(out["is_focal"].sum())
    logger.info(
        "normalize.done",
        rows=len(out),
        focal_rows=focal_rows,
        distinct_molecules=len({m for row in molecules for m in row}),
        distinct_brand_roots=int(out["brand_root"].nunique()),
    )
    if focal_rows == 0:
        logger.warning(
            "normalize.focal_company_absent",
            focal_company=focal_company,
            hint="Right-to-win scores will all be zero. Check market.focal_company.",
        )
    return out


__all__ = [
    "BRAND_MODIFIER_TOKENS",
    "SALT_SUFFIXES",
    "brand_root",
    "normalize_cardiac_frame",
    "split_molecules",
]
