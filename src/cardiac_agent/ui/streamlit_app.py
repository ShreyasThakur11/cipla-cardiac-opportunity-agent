"""Streamlit console.

The surface used to present the work. Five tabs, in the order the case
questions are asked:

1. **Overview** - the market, and where Cipla stands in it.
2. **Prioritisation** - the two-axis scorecard and the ranked spaces.
3. **Deep dive** - the evidence card for any single space.
4. **Whitespace and forecast** - underpenetration and the three-to-five-year view.
5. **Ask the agent** - free-text questions, with the trace and evidence visible.

Everything renders from the same :class:`AnalysisContext` the CLI and API use,
so what is on screen cannot drift from what the agent answers.

Run with:  ``streamlit run src/cardiac_agent/ui/streamlit_app.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `streamlit run path/to/streamlit_app.py` without an editable install.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from cardiac_agent.analytics.forecast import forecast_space  # noqa: E402
from cardiac_agent.analytics.sensitivity import run_sensitivity  # noqa: E402
from cardiac_agent.analytics.whitespace import find_whitespace  # noqa: E402
from cardiac_agent.config import get_settings  # noqa: E402
from cardiac_agent.pipeline import WarehouseMissingError, get_context  # noqa: E402

st.set_page_config(
    page_title="Cardiac Opportunity Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

LEVEL_LABELS = {
    "segment": "Segment",
    "sub_segment": "Sub-segment",
    "molecule_class": "Molecule class",
    "molecule_combination": "Molecule / combination",
    "treatment_archetype": "Treatment archetype",
    "anchor_molecule": "Anchor molecule",
}


@st.cache_resource(show_spinner="Building the analysis context...")
def load_context():
    return get_context()


@st.cache_resource(show_spinner="Starting the agent...")
def load_agent():
    from cardiac_agent.agent import build_agent

    return build_agent(load_context())


@st.cache_data(show_spinner="Running sensitivity analysis...")
def cached_sensitivity(level: str, top_k: int):
    context = load_context()
    result = run_sensitivity(
        context.enriched, level=level, framework=context.framework, top_k=top_k
    )
    return result.stability


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


try:
    context = load_context()
except WarehouseMissingError as exc:
    st.error(str(exc))
    st.info("Place the workbook in `data/raw/` and run `cardiac-agent build`, then reload.")
    st.stop()

settings = get_settings()
totals = context.totals

# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("Cardiac Opportunity Agent")
    st.caption(
        f"India Cardiac market, MAT {context.as_of}. "
        f"{len(context.scored)} opportunity spaces scored across six levels."
    )
    st.metric("Market size", f"₹{totals['market_value_t2']:,.0f} cr", _pct(totals["market_yoy"]))
    st.metric(
        "Cipla",
        f"₹{totals['focal_value_t2']:,.0f} cr",
        f"{_pct(totals['focal_yoy'])} vs market {_pct(totals['market_yoy'])}",
        delta_color="inverse" if totals["focal_yoy"] < totals["market_yoy"] else "normal",
    )
    st.metric("Cipla share", _pct(totals["focal_share"]))

    st.divider()
    st.caption("**Model**")
    if settings.llm_available:
        st.success(f"{settings.llm_provider} / {settings.llm_model}")
    else:
        st.warning(
            "No model credentials. The agent answers deterministically: every number is "
            "identical, only the prose is templated."
        )

    st.caption("**Data lineage**")
    st.code(
        f"source  {Path(str(context.metadata.get('source_file', ''))).name}\n"
        f"sha256  {str(context.metadata.get('source_sha256', ''))[:16]}...\n"
        f"built   {context.metadata.get('built_at', '')}\n"
        f"rows    {context.metadata.get('sku_rows', 0):,}",
        language=None,
    )

overview_tab, priority_tab, deep_tab, future_tab, agent_tab = st.tabs(
    ["Overview", "Prioritisation", "Deep dive", "Whitespace and forecast", "Ask the agent"]
)

# ---------------------------------------------------------------- overview

with overview_tab:
    st.subheader("The market, and where the growth actually comes from")

    columns = st.columns(4)
    columns[0].metric("Reported growth", _pct(totals["market_yoy"]))
    columns[1].metric("Real demand growth", _pct(totals["market_real_growth"]))
    columns[2].metric("Volume growth", _pct(totals["market_volume_growth"]))
    columns[3].metric("Price contribution", _pct(totals["market_price_effect"]))

    st.caption(
        "Reported value growth splits into demand and price. Constant-price MAT holds "
        "prices at the prior year, so its growth is demand; the residual is price. Roughly "
        f"{_pct(totals['market_price_effect'])} of the headline "
        f"{_pct(totals['market_yoy'])} is price, which does not compound the way "
        "prescription volume does."
    )

    segments = context.enriched[context.enriched["level"] == "segment"].copy()
    left, right = st.columns([1, 1])
    with left:
        figure = px.bar(
            segments.sort_values("value_t2"),
            x="value_t2",
            y="space_label",
            orientation="h",
            labels={"value_t2": "MAT value (₹ crore)", "space_label": ""},
            title="Segment size",
        )
        figure.update_layout(height=320, showlegend=False)
        st.plotly_chart(figure, use_container_width=True)
    with right:
        melted = segments.melt(
            id_vars="space_label",
            value_vars=["value_yoy", "real_growth", "volume_growth"],
            var_name="measure",
            value_name="growth",
        )
        melted["measure"] = melted["measure"].map(
            {"value_yoy": "Reported", "real_growth": "Real (constant price)", "volume_growth": "Volume"}
        )
        melted["growth"] = melted["growth"] * 100.0
        figure = px.bar(
            melted,
            x="space_label",
            y="growth",
            color="measure",
            barmode="group",
            labels={"growth": "Growth (%)", "space_label": "", "measure": ""},
            title="Reported growth against real demand",
        )
        figure.update_layout(height=320, legend={"orientation": "h", "y": -0.2})
        st.plotly_chart(figure, use_container_width=True)

    st.divider()
    st.subheader("Sub-segments")
    sub = context.scored[context.scored["level"] == "sub_segment"].sort_values(
        "value_t2", ascending=False
    )
    st.dataframe(
        sub[
            [
                "space_label",
                "value_t2",
                "value_yoy",
                "real_growth",
                "volume_growth",
                "hhi",
                "n_players",
                "leader_company",
                "focal_share_t2",
                "strategic_verdict",
            ]
        ].rename(
            columns={
                "space_label": "Sub-segment",
                "value_t2": "MAT (₹ cr)",
                "value_yoy": "Growth",
                "real_growth": "Real growth",
                "volume_growth": "Volume growth",
                "hhi": "HHI",
                "n_players": "Players",
                "leader_company": "Leader",
                "focal_share_t2": "Cipla share",
                "strategic_verdict": "Verdict",
            }
        ),
        column_config={
            "Growth": st.column_config.NumberColumn(format="%.1f%%"),
            "Real growth": st.column_config.NumberColumn(format="%.1f%%"),
            "Volume growth": st.column_config.NumberColumn(format="%.1f%%"),
            "Cipla share": st.column_config.NumberColumn(format="%.2f%%"),
            "MAT (₹ cr)": st.column_config.NumberColumn(format="%.0f"),
        },
        hide_index=True,
        use_container_width=True,
    )

# ------------------------------------------------------------ prioritisation

with priority_tab:
    st.subheader("Two scores, deliberately kept apart")
    st.caption(
        "The Market Opportunity Index rates a space for anybody. The Cipla Priority Score "
        "is that index passed through a right-to-win gate. A space high on the first and "
        "low on the second is a real opportunity that somebody else is positioned to win, "
        "and naming those is as useful as naming the targets."
    )

    control_left, control_right = st.columns([2, 1])
    level = control_left.selectbox(
        "Level",
        options=list(LEVEL_LABELS),
        format_func=lambda key: LEVEL_LABELS[key],
        index=list(LEVEL_LABELS).index("molecule_combination"),
    )
    top_n = control_right.slider("Rows", min_value=5, max_value=30, value=12)

    frame = context.scored[context.scored["level"] == level].copy()
    if frame.empty:
        st.warning("No spaces at this level cleared the size and player-count filters.")
    else:
        frame["Bubble"] = frame["value_t2"].clip(lower=1.0)
        figure = px.scatter(
            frame,
            x="right_to_win_score",
            y="market_opportunity_index",
            size="Bubble",
            color="strategic_verdict",
            hover_name="space_label",
            hover_data={
                "value_t2": ":,.0f",
                "value_yoy": ":.1%",
                "real_growth": ":.1%",
                "hhi": ":,.0f",
                "focal_share_t2": ":.2%",
                "Bubble": False,
            },
            labels={
                "right_to_win_score": "Right to win",
                "market_opportunity_index": "Market opportunity",
                "strategic_verdict": "Verdict",
            },
            title="Where to play: opportunity against right to win (bubble size is market value)",
        )
        figure.add_hline(y=70, line_dash="dot", line_color="grey")
        figure.add_vline(x=70, line_dash="dot", line_color="grey")
        figure.update_layout(height=520, legend={"orientation": "h", "y": -0.18})
        st.plotly_chart(figure, use_container_width=True)

        rank_by = st.radio(
            "Rank by",
            options=["cipla_priority_score", "market_opportunity_index"],
            format_func=lambda key: (
                "Cipla Priority Score (what Cipla should do)"
                if key == "cipla_priority_score"
                else "Market Opportunity Index (what is attractive for anyone)"
            ),
            horizontal=True,
        )
        ranked = frame.sort_values(rank_by, ascending=False).head(top_n)
        st.dataframe(
            ranked[
                [
                    "space_label",
                    "value_t2",
                    "value_yoy",
                    "real_growth",
                    "hhi",
                    "leader_company",
                    "leader_share",
                    "focal_share_t2",
                    "trend_multiplier",
                    "market_opportunity_index",
                    "right_to_win_score",
                    "cipla_priority_score",
                    "strategic_verdict",
                ]
            ].rename(
                columns={
                    "space_label": "Space",
                    "value_t2": "MAT (₹ cr)",
                    "value_yoy": "Growth",
                    "real_growth": "Real growth",
                    "hhi": "HHI",
                    "leader_company": "Leader",
                    "leader_share": "Leader share",
                    "focal_share_t2": "Cipla share",
                    "trend_multiplier": "Signal tilt",
                    "market_opportunity_index": "Opportunity",
                    "right_to_win_score": "Right to win",
                    "cipla_priority_score": "Priority",
                    "strategic_verdict": "Verdict",
                }
            ),
            column_config={
                "Growth": st.column_config.NumberColumn(format="%.1f%%"),
                "Real growth": st.column_config.NumberColumn(format="%.1f%%"),
                "Leader share": st.column_config.NumberColumn(format="%.1f%%"),
                "Cipla share": st.column_config.NumberColumn(format="%.2f%%"),
                "MAT (₹ cr)": st.column_config.NumberColumn(format="%.0f"),
                "Opportunity": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                "Right to win": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                "Priority": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            },
            hide_index=True,
            use_container_width=True,
        )

        with st.expander("How robust is this ranking to the weights?"):
            st.caption(
                "Every weight block is redrawn from a Dirichlet distribution centred on the "
                "configured values and the market re-scored 500 times. Above 0.80 the "
                "recommendation survives almost any reasonable weighting. Below 0.60 it is a "
                "judgement call and should be presented as one."
            )
            stability = cached_sensitivity(level, 5)
            st.dataframe(
                stability.head(12).rename(
                    columns={
                        "space_label": "Space",
                        "baseline_rank": "Base rank",
                        "top_k_frequency": "In top 5",
                        "mean_rank": "Mean rank",
                        "worst_rank": "Worst rank",
                    }
                )[["Space", "Base rank", "In top 5", "Mean rank", "Worst rank"]],
                column_config={
                    "In top 5": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")
                },
                hide_index=True,
                use_container_width=True,
            )

# --------------------------------------------------------------- deep dive

with deep_tab:
    st.subheader("Evidence card")
    level_choice = st.selectbox(
        "Level",
        options=list(LEVEL_LABELS),
        format_func=lambda key: LEVEL_LABELS[key],
        index=list(LEVEL_LABELS).index("molecule_combination"),
        key="deep_level",
    )
    candidates = context.scored[context.scored["level"] == level_choice].sort_values(
        "cipla_priority_score", ascending=False
    )
    if candidates.empty:
        st.warning("No spaces at this level.")
    else:
        choice = st.selectbox("Space", options=candidates["space_label"].tolist())
        row = candidates[candidates["space_label"] == choice].iloc[0]

        metric_columns = st.columns(5)
        metric_columns[0].metric("MAT value", f"₹{row['value_t2']:,.0f} cr", _pct(row["value_yoy"]))
        metric_columns[1].metric("Real demand growth", _pct(row["real_growth"]))
        metric_columns[2].metric("Volume growth", _pct(row["volume_growth"]))
        metric_columns[3].metric("Concentration", f"HHI {row['hhi']:,.0f}", row["concentration_label"])
        metric_columns[4].metric("Cipla share", _pct(row["focal_share_t2"]), f"{row['focal_share_delta_pp']:+.2f} pp")

        score_left, score_right = st.columns([1, 1])
        with score_left:
            pillars = pd.DataFrame(
                {
                    "Pillar": [
                        "Market attractiveness",
                        "Future potential",
                        "Competitive headroom",
                        "Right to win",
                    ],
                    "Score": [
                        row["pillar__market_attractiveness"],
                        row["pillar__future_potential"],
                        row["pillar__competitive_headroom"],
                        row["pillar__right_to_win"],
                    ],
                }
            )
            figure = px.bar(
                pillars,
                x="Score",
                y="Pillar",
                orientation="h",
                range_x=[0, 100],
                title=f"Score breakdown - priority {row['cipla_priority_score']:.1f}",
            )
            figure.update_layout(height=300)
            st.plotly_chart(figure, use_container_width=True)
        with score_right:
            competitors = context.company_facts[
                (context.company_facts["level"] == row["level"])
                & (context.company_facts["space_id"] == row["space_id"])
            ].nlargest(8, "value_t2")
            figure = px.bar(
                competitors.sort_values("value_t2"),
                x="value_t2",
                y="company_clean",
                orientation="h",
                labels={"value_t2": "MAT value (₹ crore)", "company_clean": ""},
                title=f"Leading players - {int(row['n_players'])} active",
            )
            figure.update_layout(height=300)
            st.plotly_chart(figure, use_container_width=True)

        st.markdown(f"**Verdict: {row['strategic_verdict']}**")
        signal_ids = [s for s in str(row.get("trend_signal_ids", "")).split(",") if s]
        if signal_ids:
            st.caption(
                f"External signals applied ({row['trend_multiplier']:.2f}x tilt): "
                + ", ".join(signal_ids)
            )
        if row.get("adjacent_cipla_brands"):
            st.caption(f"Adjacent Cipla brands that could be extended: {row['adjacent_cipla_brands']}")

# ------------------------------------------------------- whitespace/forecast

with future_tab:
    st.subheader("Underpenetrated spaces with a route in")
    st.caption(
        "A space qualifies when its opportunity index is high, Cipla's share sits below "
        "three quarters of its therapy-area share, and there is a molecule or brand route "
        "in. Anchor-molecule rows overlap the hierarchical levels by design, so read them "
        "as franchises rather than adding them up."
    )
    gaps = find_whitespace(
        context.scored,
        focal_overall_share=totals["focal_share"],
        levels=["sub_segment", "molecule_combination", "anchor_molecule"],
        limit=12,
    )
    if gaps.empty:
        st.info("No space cleared all three tests.")
    else:
        st.dataframe(
            gaps[
                [
                    "space_label",
                    "level",
                    "value_t2",
                    "focal_share_t2",
                    "penetration_index",
                    "value_gap_cr",
                    "market_opportunity_index",
                    "route_to_win",
                ]
            ].rename(
                columns={
                    "space_label": "Space",
                    "level": "Level",
                    "value_t2": "MAT (₹ cr)",
                    "focal_share_t2": "Cipla share",
                    "penetration_index": "Penetration index",
                    "value_gap_cr": "Gap to fair share (₹ cr)",
                    "market_opportunity_index": "Opportunity",
                    "route_to_win": "Route in",
                }
            ),
            column_config={
                "Cipla share": st.column_config.NumberColumn(format="%.2f%%"),
                "MAT (₹ cr)": st.column_config.NumberColumn(format="%.0f"),
                "Gap to fair share (₹ cr)": st.column_config.NumberColumn(format="%.1f"),
            },
            hide_index=True,
            use_container_width=True,
        )

    st.divider()
    st.subheader("Three-to-five year projection")
    horizon = st.slider("Horizon (years)", min_value=3, max_value=5, value=5)
    forecast_level = st.selectbox(
        "Level",
        options=list(LEVEL_LABELS),
        format_func=lambda key: LEVEL_LABELS[key],
        index=list(LEVEL_LABELS).index("sub_segment"),
        key="forecast_level",
    )
    subset = context.scored[context.scored["level"] == forecast_level].nlargest(
        10, "cipla_priority_score"
    )
    records = []
    for _, candidate in subset.iterrows():
        projection = forecast_space(
            candidate,
            market_cagr=totals["market_cagr_2y"],
            framework=context.framework,
            horizon_years=horizon,
        )
        records.append(projection.to_dict())
    if records:
        projections = pd.DataFrame(records)
        figure = px.scatter(
            projections,
            x="base_value_cr",
            y="base_cagr_pct",
            size="projected_value_cr",
            hover_name="space_label",
            labels={
                "base_value_cr": "Current MAT value (₹ crore)",
                "base_cagr_pct": f"Projected {horizon}-year CAGR (%)",
            },
            title="Projected growth against current size",
        )
        figure.add_hline(
            y=totals["market_cagr_2y"] * 100.0,
            line_dash="dash",
            annotation_text=f"Market {totals['market_cagr_2y'] * 100:.1f}%",
        )
        figure.update_layout(height=430)
        st.plotly_chart(figure, use_container_width=True)

        st.dataframe(
            projections[
                [
                    "space_label",
                    "base_value_cr",
                    "base_cagr_pct",
                    "bear_value_cr",
                    "projected_value_cr",
                    "bull_value_cr",
                    "outperformance_pp",
                ]
            ].rename(
                columns={
                    "space_label": "Space",
                    "base_value_cr": "Today (₹ cr)",
                    "base_cagr_pct": "CAGR %",
                    "bear_value_cr": "Bear",
                    "projected_value_cr": "Base",
                    "bull_value_cr": "Bull",
                    "outperformance_pp": "vs market (pp)",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Projections mean-revert towards the therapy-area rate and are capped. They are "
            "a structured extrapolation of two years of history, not a plan."
        )

# --------------------------------------------------------------- ask agent

with agent_tab:
    st.subheader("Ask the agent")
    st.caption(
        "The agent plans, calls tools, drafts an answer and verifies every number in it "
        "against the evidence before returning. If a figure cannot be traced to a tool "
        "result, the draft is rejected and rewritten."
    )

    examples = [
        "What are the top 5 opportunity spaces and which 2-3 should Cipla prioritise?",
        "Which attractive spaces are underpenetrated by Cipla today, and what would it take to build a position?",
        "What is Cipla's right to win in statin combinations compared with the leaders?",
        "Where should Cipla double down, build capability, be selective, or avoid investing?",
        "Is the growth in Other Lipid Reducers something Cipla can actually access?",
    ]
    picked = st.selectbox("Example questions", options=["(write your own)", *examples])
    default = "" if picked == "(write your own)" else picked
    question = st.text_area("Question", value=default, height=90)

    if st.button("Ask", type="primary", disabled=not question.strip()):
        agent = load_agent()
        with st.spinner("Planning, gathering evidence and verifying..."):
            result = agent.ask(question)

        st.markdown(result.answer)

        if result.state.deterministic:
            st.info(
                "Answered by the deterministic renderer. Every figure comes from the "
                "analytics engine."
            )
        guard = result.state.guardrails
        if guard and guard.grounding:
            if guard.grounding.passed:
                st.success(
                    f"Numeric grounding passed: all {guard.grounding.checked} figures traced "
                    "to a tool result."
                )
            else:
                st.warning(guard.grounding.message())
        for warning in result.state.warnings:
            st.warning(warning)

        if result.citations:
            with st.expander("Sources"):
                for citation in result.citations:
                    line = f"**[{citation['id']}]** {citation['title']} - {citation['publisher']}"
                    if citation["url"] and not citation["url"].startswith("internal://"):
                        line += f"  \n{citation['url']}"
                    st.markdown(line)

        with st.expander("Execution trace"):
            st.json(result.state.to_trace())
        with st.expander("Evidence pack"):
            st.json(result.evidence)
