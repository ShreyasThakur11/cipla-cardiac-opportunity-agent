"""Deterministic narrative rendering.

This is what the agent answers with when no language model is available, or
when the model's draft cannot be grounded after its rewrite budget is spent.

It is not a degraded mode in any way that matters. The analysis is identical -
same scores, same rankings, same forecasts - because the model was never
producing those. What is lost is fluency and the ability to answer an
unanticipated question shape. What is gained is a system that cannot fail in
front of a panel because a key expired.

For the live demonstration this is the safety net: the agent always answers,
and the answer is always the same one the deterministic engine computed.
"""

from __future__ import annotations

from typing import Any

from ..pipeline import AnalysisContext


def _fmt_cr(value: Any) -> str:
    try:
        return f"{float(value):,.0f} crore"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f} per cent"
    except (TypeError, ValueError):
        return str(value)


def _rank_table(spaces: list[dict[str, Any]], limit: int = 5) -> str:
    if not spaces:
        return "No spaces cleared the filters."
    lines = [
        "| Space | Size | Real growth | Concentration | Cipla share | Opportunity | Right to win | Priority |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in spaces[:limit]:
        lines.append(
            "| {label} | {size} | {real} | HHI {hhi:,.0f} | {share} | {moi:.1f} | {rtw:.1f} | {cps:.1f} |".format(
                label=row.get("space_label", ""),
                size=_fmt_cr(row.get("value_t2")),
                real=_fmt_pct(row.get("real_growth_pct")),
                hhi=float(row.get("hhi") or 0.0),
                share=_fmt_pct(row.get("focal_share_t2_pct")),
                moi=float(row.get("market_opportunity_index") or 0.0),
                rtw=float(row.get("right_to_win_score") or 0.0),
                cps=float(row.get("cipla_priority_score") or 0.0),
            )
        )
    return "\n".join(lines)


def render_answer(question: str, evidence: dict[str, Any], context: AnalysisContext) -> str:
    """Compose an answer from the evidence pack without a language model."""
    parts: list[str] = []

    overview = evidence.get("market_overview")
    if overview:
        parts.append(
            "The India Cardiac market covered by this dataset is worth "
            f"{_fmt_cr(overview['market_value_cr'])} on a moving annual total to "
            f"{overview['as_of']}, growing {_fmt_pct(overview['market_growth_pct'])} year on year. "
            f"Stripping out price, real demand grew {_fmt_pct(overview['market_real_growth_pct'])} "
            f"and volume {_fmt_pct(overview['market_volume_growth_pct'])}, so roughly "
            f"{_fmt_pct(overview['market_price_effect_pct'])} of the headline growth is price. "
            f"{overview['focal_company']} holds {_fmt_cr(overview['focal_value_cr'])}, a share of "
            f"{_fmt_pct(overview['focal_share_pct'])}, and grew "
            f"{_fmt_pct(overview['focal_growth_pct'])}, which is "
            f"{abs(float(overview['focal_growth_gap_pp'])):.1f} percentage points "
            f"{'behind' if float(overview['focal_growth_gap_pp']) < 0 else 'ahead of'} the market."
        )

    ranking_keys = [key for key in evidence if key.startswith("rank_opportunity_spaces")]
    for key in ranking_keys:
        block = evidence[key]
        heading = (
            "Top opportunity spaces"
            if block.get("ranked_by") == "market_opportunity_index"
            else "Priority spaces for Cipla"
        )
        parts.append(
            f"**{heading}** at the {block['level'].replace('_', ' ')} level, ranked by "
            f"{block['ranked_by'].replace('_', ' ')}:\n\n" + _rank_table(block.get("spaces", []))
        )

    deep_dive_keys = [key for key in evidence if key.startswith("space_deep_dive")]
    for key in deep_dive_keys:
        card = evidence[key]
        size = card["size_and_growth"]
        competition = card["competition"]
        position = card["cipla_position"]
        scores = card["scores"]
        parts.append(
            f"**{card['space_label']}** is worth {_fmt_cr(size['value_cr'])} and grew "
            f"{_fmt_pct(size['value_growth_pct'])}, of which "
            f"{_fmt_pct(size['real_growth_pct'])} is real demand and "
            f"{_fmt_pct(size['price_effect_pct'])} is price. Volume moved "
            f"{_fmt_pct(size['volume_growth_pct'])}. The space is {competition['concentration'].lower()} "
            f"at an HHI of {competition['hhi']:,.0f} across {competition['players']} players, led by "
            f"{competition['leader']} on {_fmt_pct(competition['leader_share_pct'])}. Cipla holds "
            f"{_fmt_pct(position['share_pct'])}. It scores {scores['market_opportunity_index']:.1f} on "
            f"market opportunity and {scores['right_to_win_score']:.1f} on right to win, giving a "
            f"priority score of {scores['cipla_priority_score']:.1f} and a verdict of "
            f"{scores['strategic_verdict'].lower()}."
        )

    competitor_keys = [key for key in evidence if key.startswith("competitor_profile")]
    for key in competitor_keys:
        block = evidence[key]
        strongholds = ", ".join(
            f"{row['space_label']} ({_fmt_cr(row['value_t2'])}, "
            f"{_fmt_pct(row.get('share_t2_pct', 0.0))} share, rank {int(row['rank_in_space'])})"
            for row in block.get("strongholds", [])[:3]
        )
        brands = ", ".join(
            f"{row['brand']} ({_fmt_cr(row['value_t2'])})"
            for row in block.get("top_brands", [])[:4]
        )
        parts.append(
            f"**{block['company']}** holds {_fmt_cr(block['cardiac_value_cr'])} in Cardiac, a "
            f"share of {_fmt_pct(block['cardiac_share_pct'])}, growing "
            f"{_fmt_pct(block['growth_pct'])}. It leads {block['leads_in_spaces']} of the "
            f"spaces it competes in. Its strongest sub-segments are {strongholds}. "
            f"Leading brands: {brands}."
        )

    whitespace = evidence.get("whitespace_scan")
    if whitespace and whitespace.get("count"):
        rows = whitespace["spaces"][:4]
        bullets = "\n".join(
            f"- {row['space_label']}: {_fmt_cr(row['value_t2'])}, Cipla at "
            f"{_fmt_pct(row['focal_share_t2_pct'])} against a fair share of "
            f"{_fmt_pct(whitespace['fair_share_benchmark_pct'])}, a gap of "
            f"{_fmt_cr(row['value_gap_cr'])}. Route in: {row['route_to_win']}."
            for row in rows
        )
        parts.append("**Underpenetrated spaces with a route in**\n\n" + bullets)

    forecast_keys = [key for key in evidence if key.startswith("forecast_space")]
    for key in forecast_keys:
        block = evidence[key]
        parts.append(
            f"Projected over {block['horizon_years']} years, {block['space_label']} grows at "
            f"{_fmt_pct(block['base_cagr_pct'])} a year to reach "
            f"{_fmt_cr(block['projected_value_cr'])}, within a band of "
            f"{_fmt_cr(block['bear_value_cr'])} to {_fmt_cr(block['bull_value_cr'])}. "
            f"That is {block['outperformance_pp']:.1f} percentage points "
            f"{'above' if block['outperformance_pp'] > 0 else 'below'} the market's "
            f"{_fmt_pct(block['market_cagr_pct'])}."
        )

    sensitivity = evidence.get("sensitivity_analysis")
    if sensitivity:
        robust = sensitivity.get("robust_space_count", 0)
        parts.append(
            f"Across {sensitivity['iterations']} randomised weightings of the framework, "
            f"{robust} space(s) stayed in the top {sensitivity['top_k']} at least 80 per cent "
            "of the time. Rankings below that threshold are judgement calls rather than "
            "robust conclusions."
        )

    signals_keys = [key for key in evidence if key.startswith("retrieve_external_signals")]
    cited: list[str] = []
    for key in signals_keys:
        for hit in evidence[key].get("hits", []):
            cited.append(f"- [{hit['signal_id']}] {hit['title']} ({hit['publisher']})")
    if cited:
        parts.append("**External signals consulted**\n\n" + "\n".join(dict.fromkeys(cited)))

    portfolio = evidence.get("cipla_portfolio")
    if portfolio:
        franchises = ", ".join(
            f"{row['brand_root']} ({_fmt_cr(row['value_t2'])})"
            for row in portfolio["umbrella_franchises"][:5]
        )
        parts.append(
            f"Cipla's cardiac estate is {_fmt_cr(portfolio['cardiac_value_cr'])} across "
            f"{portfolio['brand_count']} brands and {portfolio['molecule_count']} molecules. "
            f"Its largest umbrella franchises are {franchises}."
        )

    if not parts:
        parts.append(
            "The tools returned no evidence for this question. Rephrase it in terms of the "
            "Cardiac market, a specific molecule or sub-segment, or Cipla's position."
        )

    parts.append(
        "_This response was composed by the deterministic renderer. Every figure comes "
        "directly from the analytics engine; no language model was involved._"
    )
    return "\n\n".join(parts)


__all__ = ["render_answer"]
