"""Attach external signals to opportunity spaces.

This is the join between the two halves of the case: "internal datasets" and
"external signals". It produces one number per space - ``trend_multiplier`` -
which feeds the future-potential pillar, plus the list of signal identifiers
that produced it so the number can be defended.

Three rules keep the mechanism honest:

**Bounded.** The multiplier is clipped to a narrow band configured in
``rag.trend_multiplier_min/max``. Secondary research can shade the ranking; it
can never overturn what the audit shows. If a space looks good only because of
a news article, that is a finding about the article, not about the space.

**Confidence-weighted.** A medium-confidence signal contributes 60 per cent of
its stated magnitude, a low-confidence one 30 per cent.

**Diminishing within a category.** Two guideline documents describing the same
clinical shift are one piece of evidence reported twice. Within a category the
strongest signal counts fully and the rest at half weight, so agreement between
sources reinforces without compounding.

**Centred within a level.** This is the rule that makes the mechanism work at
all. Several signals - disease burden, the screening programme, price control -
apply to nearly every space in the market. Left uncorrected they add the same
constant everywhere, which pushes every multiplier into the ceiling and turns a
discriminating input into a flat one. So the raw tilt is centred on the median
tilt of its level before the multiplier is formed. A signal that applies to
everything therefore moves nothing, which is the honest treatment: it is
context for the therapy area, not a reason to prefer one space over another.
Only *differential* evidence changes the ranking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from ..config import get_framework
from ..logging_config import get_logger
from .corpus import Signal, SignalCorpus

logger = get_logger(__name__)

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")

#: Weight applied to every signal in a category after the strongest one.
SECONDARY_SIGNAL_WEIGHT = 0.5


@dataclass
class SpaceSignalLink:
    """Why one signal was attached to one space."""

    space_id: str
    level: str
    signal_id: str
    match_reason: str
    contribution: float


def space_molecule_sets(
    sku_facts: pd.DataFrame, membership: pd.DataFrame
) -> dict[tuple[str, str], set[str]]:
    """Canonical molecules present in every space, keyed by ``(level, space_id)``."""
    facts = sku_facts.reset_index(drop=False).rename(columns={"index": "row_id"})
    joined = membership.merge(
        facts[["row_id", "molecule_canonical"]],
        on="row_id",
        how="left",
        validate="many_to_one",
    )
    result: dict[tuple[str, str], set[str]] = {}
    for (level, space_id), group in joined.groupby(["level", "space_id"], sort=False):
        molecules: set[str] = set()
        for signature in group["molecule_canonical"].astype(str):
            molecules.update(part.strip().upper() for part in signature.split("+") if part.strip())
        result[(str(level), str(space_id))] = molecules
    return result


def _match(
    signal: Signal,
    *,
    label: str,
    segment: str,
    sub_segment: str,
    molecules: set[str],
) -> tuple[bool, str]:
    """Decide whether a signal applies to a space, and say why."""
    label_upper = label.upper()
    label_words = {word.lower() for word in _WORD.findall(label)}

    hit_molecules = sorted(
        molecule
        for molecule in signal.molecules
        if molecule in molecules or molecule in label_upper
    )
    if hit_molecules:
        return True, f"molecule match: {', '.join(hit_molecules[:3])}"

    if signal.sub_segments and any(
        target.strip().lower() == sub_segment.strip().lower()
        or target.strip().lower() in label.lower()
        for target in signal.sub_segments
    ):
        return True, f"sub-segment match: {sub_segment or label}"

    if signal.segments and any(
        target.strip().lower() == segment.strip().lower() for target in signal.segments
    ):
        return True, f"segment match: {segment}"

    if signal.keywords:
        overlap = sorted(
            keyword
            for keyword in signal.keywords
            if keyword in label.lower() or keyword in label_words
        )
        if overlap:
            return True, f"keyword match: {', '.join(overlap[:3])}"

    return False, ""


def link_signals_to_spaces(
    spaces: pd.DataFrame,
    corpus: SignalCorpus,
    *,
    sku_facts: pd.DataFrame | None = None,
    membership: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[SpaceSignalLink]]:
    """Compute a bounded trend multiplier for every space.

    Args:
        spaces: Space frame.
        corpus: Loaded signal corpus.
        sku_facts: SKU table, used to derive the molecules in each space.
        membership: SKU-to-space map.

    Returns:
        ``(spaces_with_multiplier, links)``. ``spaces_with_multiplier`` gains
        ``trend_multiplier`` and ``trend_signal_ids``; ``links`` records every
        signal-to-space attachment and its contribution, for the audit trail.
    """
    framework = get_framework()
    lower = float(framework.get_path("rag.trend_multiplier_min", 0.80))
    upper = float(framework.get_path("rag.trend_multiplier_max", 1.25))

    out = spaces.copy()
    if not len(corpus):
        out["trend_multiplier"] = 1.0
        out["trend_signal_ids"] = ""
        logger.warning("linker.empty_corpus", spaces=len(out))
        return out, []

    molecule_index: dict[tuple[str, str], set[str]] = {}
    if sku_facts is not None and membership is not None:
        molecule_index = space_molecule_sets(sku_facts, membership)

    multipliers: list[float] = []
    signal_ids: list[str] = []
    links: list[SpaceSignalLink] = []

    for _, row in out.iterrows():
        level = str(row.get("level", ""))
        space_id = str(row.get("space_id", ""))
        label = str(row.get("space_label", ""))
        segment = str(row.get("segment", ""))
        sub_segment = str(row.get("sub_segment", ""))
        molecules = molecule_index.get((level, space_id), set())

        # Bucket contributions by category so agreement is rewarded once.
        by_category: dict[str, list[tuple[Signal, str]]] = {}
        for signal in corpus:
            if abs(signal.signed_magnitude) < 1e-9:
                continue  # background or interpretive signals carry no tilt
            matched, reason = _match(
                signal,
                label=label,
                segment=segment,
                sub_segment=sub_segment,
                molecules=molecules,
            )
            if matched:
                by_category.setdefault(signal.category, []).append((signal, reason))

        total = 0.0
        matched_ids: list[str] = []
        for category, entries in by_category.items():
            ordered = sorted(entries, key=lambda pair: abs(pair[0].signed_magnitude), reverse=True)
            for position, (signal, reason) in enumerate(ordered):
                weight = 1.0 if position == 0 else SECONDARY_SIGNAL_WEIGHT
                contribution = signal.signed_magnitude * weight
                total += contribution
                matched_ids.append(signal.id)
                links.append(
                    SpaceSignalLink(
                        space_id=space_id,
                        level=level,
                        signal_id=signal.id,
                        match_reason=f"{reason} (category {category}, weight {weight:.1f})",
                        contribution=round(contribution, 4),
                    )
                )

        multipliers.append(total)
        signal_ids.append(",".join(sorted(set(matched_ids))))

    # Centre within level, then bound. See the module docstring: a signal that
    # applies to every space carries no information about which space to pick,
    # so it must not move the ranking.
    raw = pd.Series(multipliers, index=out.index, dtype=float)
    baseline = raw.groupby(out["level"]).transform("median")
    out["trend_tilt_raw"] = raw
    out["trend_tilt_baseline"] = baseline
    out["trend_multiplier"] = (1.0 + (raw - baseline)).clip(lower, upper)
    out["trend_signal_ids"] = signal_ids

    values = out["trend_multiplier"]
    logger.info(
        "linker.done",
        spaces=len(out),
        tilted=int((values.sub(1.0).abs() > 1e-6).sum()),
        links=len(links),
        min_multiplier=round(float(values.min()), 3) if len(values) else 1.0,
        max_multiplier=round(float(values.max()), 3) if len(values) else 1.0,
    )
    return out, links


__all__ = [
    "SECONDARY_SIGNAL_WEIGHT",
    "SpaceSignalLink",
    "link_signals_to_spaces",
    "space_molecule_sets",
]
