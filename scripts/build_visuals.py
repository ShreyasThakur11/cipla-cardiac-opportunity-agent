"""Render every chart used by the documentation site and the deck.

Charts are generated from the live analysis rather than drawn by hand, so a
figure in the deck cannot disagree with the scorecard behind it. Re-run this
after any change to the data or the framework:

    python scripts/build_visuals.py

Output goes to ``docs/assets/``. PNG at 200 dpi for the deck, SVG for the web,
so the site stays sharp at any zoom without shipping large binaries.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from cardiac_agent.analytics.forecast import forecast_space  # noqa: E402
from cardiac_agent.analytics.sensitivity import run_sensitivity  # noqa: E402
from cardiac_agent.analytics.whitespace import find_whitespace  # noqa: E402
from cardiac_agent.pipeline import get_context  # noqa: E402

ASSETS = PROJECT_ROOT / "docs" / "assets"

# A restrained palette. Two accents carry meaning (priority and caution);
# everything else is neutral so the reader's eye goes to the data.
INK = "#1c2733"
MUTED = "#7d8a99"
GRID = "#e3e8ee"
PRIORITY = "#1f6f6b"
CAUTION = "#b4552d"
NEUTRAL = "#54677d"
LIGHT = "#c8d2dd"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.titlepad": 14,
        "axes.labelsize": 10,
        "axes.labelcolor": INK,
        "axes.edgecolor": GRID,
        "axes.linewidth": 0.9,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.28,
    }
)


def _style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.title.set_color(INK)


def _save(fig, name: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg"):
        fig.savefig(ASSETS / f"{name}.{suffix}")
    plt.close(fig)
    print(f"  {name}.png / .svg")


def _place_labels(ax, points, *, x_gap: float, y_gap: float) -> None:
    """Annotate scatter points, moving a label below when it would collide.

    Written rather than imported because the alternative (adjustText) is a
    dependency for one chart, and a greedy two-position rule handles a dozen
    labelled points without one.
    """
    placed: list[tuple[float, float]] = []
    for x, y, text in sorted(points, key=lambda item: -item[1]):
        above = True
        for px, py in placed:
            if abs(px - x) < x_gap and abs(py - y) < y_gap:
                above = False
                break
        ax.annotate(
            text,
            xy=(x, y),
            xytext=(0, 13 if above else -19),
            textcoords="offset points",
            ha="center",
            fontsize=8.8,
            color=INK,
        )
        placed.append((x, y))


def _short(label: str, limit: int = 34) -> str:
    """Trim a space label to something a chart axis can carry."""
    text = label.split("|")[-1].strip()
    text = text.replace("CILNIDIPINE", "Cilnidipine").replace("TELMISARTAN", "Telmisartan")
    text = text.replace("ROSUVASTATIN", "Rosuvastatin").replace("EZETIMIBE", "Ezetimibe")
    text = text.replace("CLOPIDOGREL", "Clopidogrel").replace("ATORVASTATIN", "Atorvastatin")
    text = text.replace("METOP.", "Metoprolol").replace("TELMI.", "Telmisartan")
    text = text.replace("CHLORTAL", "Chlortalidone").replace("CILNIDIP", "Cilnidipine")
    text = text.replace("TELMIS", "Telmisartan").replace("SAROGLITAZAR", "Saroglitazar")
    # Drop the leading ATC code, which means nothing to a reader.
    parts = text.split(None, 1)
    if parts and len(parts[0]) >= 5 and parts[0][0].isalpha() and any(c.isdigit() for c in parts[0]):
        text = parts[1] if len(parts) > 1 else text
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# 1. Where the market's growth actually comes from
# ---------------------------------------------------------------------------


def chart_growth_decomposition(context) -> None:
    segments = context.enriched[context.enriched["level"] == "segment"].sort_values(
        "value_t2", ascending=False
    )
    labels = [_short(v) for v in segments["space_label"]]
    reported = segments["value_yoy"].to_numpy() * 100
    real = segments["real_growth"].to_numpy() * 100
    volume = segments["volume_growth"].to_numpy() * 100

    x = np.arange(len(labels))
    width = 0.26

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.bar(x - width, reported, width, label="Reported value", color=LIGHT)
    ax.bar(x, real, width, label="Real demand (constant price)", color=PRIORITY)
    ax.bar(x + width, volume, width, label="Volume", color=NEUTRAL)

    for index, (rep, rl) in enumerate(zip(reported, real, strict=False)):
        ax.annotate(
            f"{rep - rl:.1f} pp price",
            xy=(index, max(rep, rl) + 0.9),
            ha="center",
            fontsize=8.5,
            color=CAUTION,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Year-on-year growth (%)")
    ax.set_title("Reported growth overstates demand in every segment")
    ax.legend(loc="upper right")
    ax.set_ylim(0, max(reported.max(), real.max()) * 1.28)
    _style(ax)
    _save(fig, "growth-decomposition")


# ---------------------------------------------------------------------------
# 2. The two-axis prioritisation view
# ---------------------------------------------------------------------------


def chart_priority_matrix(context, level: str = "sub_segment") -> None:
    frame = context.scored[context.scored["level"] == level].copy()

    fig, ax = plt.subplots(figsize=(9.4, 6.2))

    ax.add_patch(Rectangle((70, 70), 32, 32, color=PRIORITY, alpha=0.05, zorder=0))
    ax.add_patch(Rectangle((0, 70), 70, 32, color=CAUTION, alpha=0.04, zorder=0))
    ax.axhline(70, color=MUTED, linestyle=(0, (4, 4)), linewidth=0.9)
    ax.axvline(70, color=MUTED, linestyle=(0, (4, 4)), linewidth=0.9)

    sizes = np.sqrt(frame["value_t2"].to_numpy()) * 4.2
    colours = [
        PRIORITY if verdict in {"Double down", "Build capability"} else
        CAUTION if verdict in {"Avoid or partner", "Harvest or exit"} else NEUTRAL
        for verdict in frame["strategic_verdict"]
    ]
    ax.scatter(
        frame["right_to_win_score"],
        frame["market_opportunity_index"],
        s=sizes,
        c=colours,
        alpha=0.66,
        edgecolors="white",
        linewidths=1.1,
        zorder=3,
    )

    # Label only what a reader needs. Everything else is context.
    named = {
        "Statins Comb.", "AHT Triple / Poly Comb.", "Oth. Lipid Red.",
        "AHT Dual Comb.", "Statins Plain", "AHT Diuretic Comb.", "Fibrates", "ARBs",
    }
    points = [
        (row["right_to_win_score"], row["market_opportunity_index"], _short(row["space_label"]))
        for _, row in frame.iterrows()
        if _short(row["space_label"]) in named
    ]
    _place_labels(ax, points, x_gap=13.0, y_gap=6.0)

    ax.text(71, 99, "Double down", fontsize=9, color=PRIORITY, weight="semibold")
    ax.text(2, 99, "Attractive, but somebody else is positioned to win",
            fontsize=9, color=CAUTION, weight="semibold")

    ax.set_xlabel("Right to win")
    ax.set_ylabel("Market opportunity")
    ax.set_title("Attractive is not the same as winnable\nBubble area is market value")
    ax.set_xlim(0, 102)
    ax.set_ylim(0, 104)
    _style(ax)
    _save(fig, f"priority-matrix-{level.replace('_', '-')}")


# ---------------------------------------------------------------------------
# 3. Top molecule combinations, ranked
# ---------------------------------------------------------------------------


def chart_top_spaces(context) -> None:
    frame = (
        context.scored[context.scored["level"] == "molecule_combination"]
        .nlargest(8, "market_opportunity_index")
        .sort_values("market_opportunity_index")
    )
    labels = [_short(v, 40) for v in frame["space_label"]]
    y = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    ax.barh(y - 0.19, frame["market_opportunity_index"], 0.36, color=NEUTRAL, label="Market opportunity")
    ax.barh(y + 0.19, frame["cipla_priority_score"], 0.36, color=PRIORITY, label="Cipla priority")

    for index, (moi, cps, size) in enumerate(
        zip(frame["market_opportunity_index"], frame["cipla_priority_score"], frame["value_t2"], strict=False)
    ):
        ax.annotate(f"{moi:.0f}", (moi + 1, index - 0.19), va="center", fontsize=8.5, color=MUTED)
        ax.annotate(f"{cps:.0f}", (cps + 1, index + 0.19), va="center", fontsize=8.5, color=PRIORITY)
        ax.annotate(
            f"{size:,.0f} cr", (2, index), va="center", fontsize=8.2, color="white", weight="semibold"
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Score")
    ax.set_xlim(0, 100)
    ax.set_title("The gap between the two bars is the right-to-win gate")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    _style(ax)
    _save(fig, "top-molecule-combinations")


# ---------------------------------------------------------------------------
# 4. Growth against concentration
# ---------------------------------------------------------------------------


def chart_growth_vs_concentration(context) -> None:
    frame = context.scored[context.scored["level"] == "sub_segment"].copy()

    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    sizes = np.sqrt(frame["value_t2"].to_numpy()) * 4.0
    ax.scatter(
        frame["hhi"],
        frame["real_growth"] * 100,
        s=sizes,
        c=[CAUTION if h >= 2500 else PRIORITY if h < 1500 else NEUTRAL for h in frame["hhi"]],
        alpha=0.66,
        edgecolors="white",
        linewidths=1.1,
        zorder=3,
    )
    ax.axvline(1500, color=MUTED, linestyle=(0, (4, 4)), linewidth=0.9)
    ax.axvline(2500, color=MUTED, linestyle=(0, (4, 4)), linewidth=0.9)
    ax.axhline(
        context.totals["market_real_growth"] * 100,
        color=MUTED,
        linestyle=(0, (2, 3)),
        linewidth=0.9,
    )
    ax.annotate(
        f"Market real growth {context.totals['market_real_growth'] * 100:.1f}%",
        xy=(4300, context.totals["market_real_growth"] * 100 + 0.9),
        fontsize=8.6,
        color=MUTED,
        ha="right",
    )
    ax.annotate("Fragmented", xy=(500, 39), fontsize=9, color=PRIORITY, weight="semibold")
    ax.annotate("Concentrated", xy=(2650, 39), fontsize=9, color=CAUTION, weight="semibold")

    points = [
        (row["hhi"], row["real_growth"] * 100, _short(row["space_label"]))
        for _, row in frame.iterrows()
        if row["value_t2"] >= 400 or row["real_growth"] >= 0.3
    ]
    _place_labels(ax, points, x_gap=620.0, y_gap=3.4)

    ax.set_xlabel("Concentration (HHI)")
    ax.set_ylabel("Real demand growth (%)")
    ax.set_title("The fastest-growing sub-segment is also the most closed")
    ax.set_ylim(-4, 44)
    _style(ax)
    _save(fig, "growth-vs-concentration")


# ---------------------------------------------------------------------------
# 5. Where Cipla stands
# ---------------------------------------------------------------------------


def chart_cipla_position(context) -> None:
    frame = (
        context.scored[context.scored["level"] == "sub_segment"]
        .nlargest(8, "focal_value_t2")
        .sort_values("focal_value_t2")
    )
    labels = [_short(v) for v in frame["space_label"]]
    y = np.arange(len(labels))

    fig, (left, right) = plt.subplots(1, 2, figsize=(11.4, 4.8), gridspec_kw={"width_ratios": [1, 1.1]})

    left.barh(y, frame["focal_value_t2"], 0.62, color=NEUTRAL)
    for index, (value, share) in enumerate(
        zip(frame["focal_value_t2"], frame["focal_share_t2"], strict=False)
    ):
        left.annotate(
            f"{value:,.0f} cr  ({share * 100:.1f}%)",
            (value + 3, index),
            va="center",
            fontsize=8.5,
            color=MUTED,
        )
    left.set_yticks(y)
    left.set_yticklabels(labels)
    left.set_xlabel("Cipla value (INR crore)")
    left.set_title("Where Cipla's money is")
    left.set_xlim(0, frame["focal_value_t2"].max() * 1.45)
    left.grid(axis="y", visible=False)
    _style(left)

    gap = (frame["focal_yoy"] - frame["value_yoy"]).to_numpy() * 100
    right.barh(y, gap, 0.62, color=[PRIORITY if g >= 0 else CAUTION for g in gap])
    right.axvline(0, color=INK, linewidth=0.9)
    for index, value in enumerate(gap):
        right.annotate(
            f"{value:+.1f} pp",
            (value + (0.8 if value >= 0 else -0.8), index),
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8.5,
            color=MUTED,
        )
    right.set_yticks(y)
    right.set_yticklabels([])
    right.set_xlabel("Cipla growth minus sub-segment growth (pp)")
    right.set_title("Whether it is gaining or losing there")
    right.set_xlim(gap.min() * 1.5, max(gap.max() * 1.8, 6))
    right.grid(axis="y", visible=False)
    _style(right)

    fig.suptitle(
        "Cipla's largest positions are the ones it is losing ground in",
        fontsize=12.5,
        fontweight="semibold",
        color=INK,
        y=1.02,
    )
    _save(fig, "cipla-position")


# ---------------------------------------------------------------------------
# 6. Underpenetration
# ---------------------------------------------------------------------------


def chart_whitespace(context) -> None:
    gaps = find_whitespace(
        context.scored,
        focal_overall_share=context.totals["focal_share"],
        levels=["anchor_molecule", "molecule_combination"],
        limit=6,
    ).sort_values("value_gap_cr")
    if gaps.empty:
        return

    labels = [_short(v, 30) for v in gaps["space_label"]]
    y = np.arange(len(labels))
    fair = gaps["fair_share_value_cr"].to_numpy()
    held = gaps["focal_value_t2"].to_numpy()

    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ax.barh(y, fair, 0.6, color=LIGHT, label="Value at fair share")
    ax.barh(y, held, 0.6, color=PRIORITY, label="Cipla holds today")

    for index, (f, h) in enumerate(zip(fair, held, strict=False)):
        ax.annotate(
            f"gap {f - h:,.0f} cr", (f + 2, index), va="center", fontsize=8.6, color=CAUTION
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("INR crore")
    ax.set_xlim(0, fair.max() * 1.34)
    ax.set_title(
        f"Reaching fair share alone. Benchmark is Cipla's "
        f"{context.totals['focal_share'] * 100:.2f}% therapy-area share"
    )
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    _style(ax)
    _save(fig, "whitespace-gap")


# ---------------------------------------------------------------------------
# 7. Robustness
# ---------------------------------------------------------------------------


def chart_sensitivity(context) -> None:
    result = run_sensitivity(
        context.enriched, level="molecule_combination", framework=context.framework, top_k=5
    )
    frame = result.stability.head(8).sort_values("top_k_frequency")
    labels = [_short(v, 38) for v in frame["space_label"]]
    y = np.arange(len(labels))
    freq = frame["top_k_frequency"].to_numpy()

    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ax.barh(
        y,
        freq,
        0.62,
        color=[PRIORITY if f >= 0.8 else NEUTRAL if f >= 0.6 else CAUTION for f in freq],
    )
    ax.axvline(0.8, color=MUTED, linestyle=(0, (4, 4)), linewidth=0.9)
    ax.axvline(0.6, color=MUTED, linestyle=(0, (2, 3)), linewidth=0.9)
    for index, value in enumerate(freq):
        ax.annotate(f"{value:.0%}", (value + 0.012, index), va="center", fontsize=8.6, color=MUTED)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 1.12)
    ax.set_xlabel(f"Share of {result.iterations} randomised weightings in which the space stayed top {result.top_k}")
    ax.set_title("Which conclusions survive a different framework")
    ax.annotate("robust", xy=(0.815, -0.62), fontsize=8.5, color=PRIORITY)
    ax.annotate("judgement call", xy=(0.2, -0.62), fontsize=8.5, color=CAUTION)
    ax.grid(axis="y", visible=False)
    _style(ax)
    _save(fig, "sensitivity")


# ---------------------------------------------------------------------------
# 8. Five-year projection
# ---------------------------------------------------------------------------


def chart_forecast(context) -> None:
    targets = [
        ("molecule_combination", "C10A0S ROSUVASTATIN + EZETIMIBE"),
        ("molecule_combination", "C02F0O CILNIDIPINE + TELMISARTAN"),
        ("sub_segment", "Anti Hypertensives | AHT Triple / Poly Comb."),
        ("sub_segment", "Lipid Regulators | Statins Comb."),
        ("sub_segment", "Anti Hypertensives | AHT Dual Comb."),
        ("sub_segment", "Anti Hypertensives | AHT Diuretic Comb."),
    ]
    rows = []
    for level, label in targets:
        row = context.find_space(label, level)
        if row is None:
            continue
        rows.append(
            forecast_space(
                row,
                market_cagr=context.totals["market_cagr_2y"],
                framework=context.framework,
                horizon_years=5,
            )
        )
    rows.sort(key=lambda f: f.outperformance_pp)
    labels = [_short(f.space_label, 34) for f in rows]
    y = np.arange(len(labels))
    outperf = np.array([f.outperformance_pp for f in rows])

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.barh(y, outperf, 0.62, color=[PRIORITY if v > 0 else CAUTION for v in outperf])
    ax.axvline(0, color=INK, linewidth=1.0)
    for index, forecast in enumerate(rows):
        ax.annotate(
            f"{forecast.base_cagr * 100:.1f}% CAGR to {forecast.projected_value_cr:,.0f} cr",
            (outperf[index] + (0.5 if outperf[index] >= 0 else -0.5), index),
            va="center",
            ha="left" if outperf[index] >= 0 else "right",
            fontsize=8.4,
            color=MUTED,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel(
        f"Projected five-year CAGR against the market's {context.totals['market_cagr_2y'] * 100:.1f}% (pp)"
    )
    ax.set_xlim(outperf.min() - 7, outperf.max() + 12)
    ax.set_title("Which spaces are projected to outperform, and by how much")
    ax.grid(axis="y", visible=False)
    _style(ax)
    _save(fig, "forecast-outperformance")


# ---------------------------------------------------------------------------
# 9. Competitive standing
# ---------------------------------------------------------------------------


def chart_competitors(context) -> None:
    """Top ten by value, with Cipla appended so the comparison is visible.

    Cipla does not reach the top ten, so a top-ten chart alone would assert a
    ranking it never shows. The rank is computed here rather than written into
    the title, so the figure cannot drift from the data behind it.
    """
    segment_rows = context.company_facts[context.company_facts["level"] == "segment"]
    totals = segment_rows.groupby("company_clean")[["value_t1", "value_t2"]].sum()
    totals["growth"] = (totals["value_t2"] / totals["value_t1"] - 1.0) * 100
    totals = totals.sort_values("value_t2", ascending=False)

    focal = context.framework.get_path("market.focal_company_label", "Cipla").upper()
    ranking = {name.upper(): position for position, name in enumerate(totals.index, start=1)}
    focal_rank = ranking.get(focal)

    top = totals.head(10)
    focal_row = totals[totals.index.str.upper() == focal]
    included_focal = focal_rank is not None and focal_rank > 10 and not focal_row.empty
    display = top if not included_focal else pd.concat([top, focal_row])
    display = display.iloc[::-1]  # smallest at the bottom of a horizontal chart

    labels = [
        f"{name}  (#{ranking[name.upper()]})" if included_focal and name.upper() == focal else name
        for name in display.index
    ]
    y = np.arange(len(labels))
    colours = [PRIORITY if name.upper() == focal else LIGHT for name in display.index]

    fig, ax = plt.subplots(figsize=(9.4, 5.4))
    ax.barh(y, display["value_t2"], 0.62, color=colours)
    market_growth = context.totals["market_yoy"] * 100

    for index, (value, growth) in enumerate(zip(display["value_t2"], display["growth"], strict=False)):
        ax.annotate(
            f"{value:,.0f} cr   {growth:+.1f}%",
            (value + 45, index),
            va="center",
            fontsize=8.6,
            color=CAUTION if growth < market_growth else MUTED,
        )

    if included_focal:
        # A visible break, so nobody reads Cipla as the eleventh largest player.
        ax.axhline(0.5, color=MUTED, linestyle=(0, (2, 3)), linewidth=0.9)
        ax.annotate(
            f"ranks {ranking[focal]} of {len(totals)}",
            xy=(display["value_t2"].max() * 0.42, 0),
            va="center",
            fontsize=8.6,
            color=PRIORITY,
            weight="semibold",
        )

    ordinal = {1: "first", 2: "second", 3: "third"}.get(focal_rank, f"{focal_rank}th")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Cardiac value, MAT (INR crore)")
    ax.set_xlim(0, display["value_t2"].max() * 1.32)
    ax.set_title(
        f"Cipla ranks {ordinal} by value and grows below the market's {market_growth:.1f}%"
    )
    ax.grid(axis="y", visible=False)
    _style(ax)
    _save(fig, "competitive-standing")


# ---------------------------------------------------------------------------
# 10. Pillar decomposition for the two priorities
# ---------------------------------------------------------------------------


def chart_pillars(context) -> None:
    targets = [
        ("sub_segment", "Lipid Regulators | Statins Comb."),
        ("sub_segment", "Anti Hypertensives | AHT Triple / Poly Comb."),
        ("sub_segment", "Lipid Regulators | Oth. Lipid Red."),
    ]
    pillars = [
        ("pillar__market_attractiveness", "Market\nattractiveness"),
        ("pillar__future_potential", "Future\npotential"),
        ("pillar__competitive_headroom", "Competitive\nheadroom"),
        ("pillar__right_to_win", "Right\nto win"),
    ]

    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    x = np.arange(len(pillars))
    width = 0.26
    colours = [PRIORITY, NEUTRAL, CAUTION]

    for offset, ((level, label), colour) in enumerate(zip(targets, colours, strict=False)):
        row = context.find_space(label, level)
        if row is None:
            continue
        values = [float(row[key]) for key, _ in pillars]
        ax.bar(
            x + (offset - 1) * width,
            values,
            width,
            label=f"{_short(label)}  (priority {row['cipla_priority_score']:.0f})",
            color=colour,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([name for _, name in pillars])
    ax.set_ylabel("Percentile score within level")
    ax.set_ylim(0, 105)
    ax.set_title("Why one space is a priority and another is not")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
    _style(ax)
    _save(fig, "pillar-decomposition")


def main() -> int:
    print("Building the analysis context...")
    context = get_context()
    print(f"Rendering charts into {ASSETS.relative_to(PROJECT_ROOT)}:")

    chart_growth_decomposition(context)
    chart_priority_matrix(context, "sub_segment")
    chart_priority_matrix(context, "molecule_combination")
    chart_top_spaces(context)
    chart_growth_vs_concentration(context)
    chart_cipla_position(context)
    chart_whitespace(context)
    chart_sensitivity(context)
    chart_forecast(context)
    chart_competitors(context)
    chart_pillars(context)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
