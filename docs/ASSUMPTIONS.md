---
title: Assumptions
layout: default
nav_order: 12
---

# Assumptions

Every judgement call in the analysis, with the reasoning and how to change it.
Anything not listed here is either read directly from the data or defined in
the organisers' glossary.

---

## About the data

**The dataset is a retail prescription audit.** Value, volume and price to
retailer by pack, brand and company, in the IQVIA-style format used across the
Indian industry. It is treated as the market, which it is not: institutional,
hospital and government-tender channels are not represented. That matters given
the scale of public screening programmes, and it is stated in the limitations
rather than adjusted for, because the dataset gives no basis for an adjustment.

**Values are in INR crore.** The workbook carries no unit label. Crore is
inferred from the total of ₹23,244 for a therapy area covering
anti-hypertensives, lipid regulators and anti-angina, which is consistent with
published estimates of the Indian cardiac market. Every output states the unit
explicitly so a misreading is visible.

**Quantities are in the pack-dependent units the glossary describes** (tablets,
millilitres or doses). They are therefore comparable within a space and not
across spaces of different dosage forms. Volume growth is used as a
within-space rate, never as a cross-space level, which is what makes this safe.

**MAT CP for the latest period is stated at the previous year's prices.** This
comes from the glossary and determines how real growth is computed: MAT CP
Feb'26 against reported MAT Feb'25, not against MAT CP Feb'25. Getting this
wrong would misstate the price contribution across the entire analysis.

**A trailing asterisk marks a consolidated corporate group.** `CIPLA*`, `SUN*`,
`ZYDUS CADILA*`. The asterisk is stripped for display and the raw value kept
for joins. Consolidated groups are the right unit for competitive analysis
because they share a field force.

**Zero-value rows are real.** Roughly 1,300 packs report zero in the latest
MAT. These are discontinued or pre-launch, not missing data, and are retained
so player counts and share churn are correct.

---

## About molecules and brands

**Salt forms are the same active ingredient.** "AMLODIPINE BESILATE" and
"AMLODIPINE" roll into one franchise, as do metoprolol succinate and tartrate.
The stripped suffix list is deliberately conservative and excludes nitrate
esters, because isosorbide mononitrate and dinitrate are genuinely different
drugs rather than salt forms of one.

The metoprolol case is a real simplification: succinate is extended-release and
tartrate is immediate-release, and they are not clinically interchangeable. For
franchise adjacency, which is what the field uses, treating them as one
molecule is correct. For a formulation decision it would not be.

**A combination pack's value splits evenly across its ingredients** when
computing molecule adjacency, so a triple FDC does not count three times over.
An even split is a simplification: the therapeutic and commercial contribution
of each component is not equal. No allocation basis exists in the data, and an
even split is at least neutral.

**Anchor-molecule spaces overlap by design.** A Cilnidipine + Telmisartan pack
counts towards both franchises, so anchor values sum to more than the market.
This is the point, and it is why anchor spaces are ranked separately rather
than pooled with the hierarchical levels. Every output that shows them says so.

**Brand root recovery is heuristic.** A hyphen is treated as an unambiguous
line-extension marker, so `AMLOPRES-AT` reduces to `AMLOPRES`. A trailing token
reduces only when it is short or a known modifier, so `ROSULIP GOLD` reduces
while `ACE REVELOL` does not. The rule is tested against real brand names in
the suite. It will occasionally be wrong on an unusual name, and the effect is
bounded: a wrong root affects one component of one pillar for one space.

---

## About the framework

**Percentile normalisation within a level.** Audit data is heavily skewed and a
common min-max scale across levels would measure list length rather than market
structure. See [PRIORITIZATION_FRAMEWORK.md](PRIORITIZATION_FRAMEWORK.html).

**Weights are judgement, and are exposed as such.** Every weight in
`config/settings.yaml` is a defensible choice rather than a derived optimum,
because there is no labelled outcome to optimise against. That is precisely why
the sensitivity analysis exists and why the agent is required to run it before
presenting a recommendation.

**Future potential outweighs current attractiveness, 40 to 34.** The case asks
which spaces will outperform over three to five years, not which are largest
today.

**Reported value growth carries no weight in future potential.** Price gains do
not compound the way prescription volume does, and a material part of the
essential cardiovascular basket sits under administered ceiling prices. It
appears in market attractiveness, where it belongs.

**The right-to-win gate is a multiplier, not a fourth pillar.** Adding it into
a single weighted score would let a very attractive, completely inaccessible
space outrank a moderately attractive winnable one. A multiplier cannot do
that, which is the behaviour the case asks for.

**The gate floor is 0.35 rather than zero.** A space Cipla cannot win today may
still be worth watching, and a zero floor would remove it from the output
entirely rather than ranking it low.

**The gate curve exponent is 1.35.** Above 1.0, so weak right to win hurts more
than linearly. For a company at 1.68 per cent therapy share, chasing growth
into spaces with no structural advantage is the failure mode to protect
against.

**Size floor of ₹100 crore.** Below this a win cannot move a company of Cipla's
size, and small bases produce unstable percentages. It is the single most
consequential filter: it removes 213 of 321 constructed spaces.

**Minimum of three active players.** Fewer than three is treated as
structurally closed, most often a single-brand or originator-held space.

---

## About the forecast

**The therapy area keeps growing ahead of the wider pharmaceutical market.**
Grounded in the disease-burden and screening evidence in the corpus, not
assumed. It is the assumption that most affects the projections and would be
the first thing to revisit against a longer history.

**Excess growth over the market decays 28 per cent a year.** Nothing sustains
45 per cent for five years, and assuming it does is how forecasts produce
indefensible numbers. The rate is a judgement calibrated so a high-growth space
lands at a plausible five-year CAGR rather than an absurd one.

**Growth is capped at 45 per cent and floored at minus 15 per cent.** Bounds on
extrapolating a two-year rate forward five years.

**Bull and bear shift the starting rate by 4 percentage points.** A band rather
than a distribution. With two observations there is no basis for a variance
estimate, and presenting one would imply precision the data does not support.

**Base rate weights: 40 per cent real growth, 30 per cent volume, 20 per cent
two-year CAGR, 10 per cent momentum.** Demand-led measures dominate, for the
same reason they dominate the future-potential pillar.

---

## About the external signals

**Fourteen documents, chosen for relevance rather than systematically
sampled.** This is curation, not a literature review, and the corpus is
therefore incomplete by construction. Its influence is bounded to a narrow band
for exactly that reason.

**Confidence weights: high 1.0, medium 0.6, low 0.3.** A judgement about how
much a stated magnitude should be trusted.

**Within a category, the strongest signal counts fully and the rest at half
weight.** Two guideline documents describing one clinical shift are one piece
of evidence reported twice.

**Tilts are centred on the median tilt of their space level.** A signal that
applies to every space carries no information about which space to prefer, so
it must not move the ranking. Without this the multiplier saturates at its
ceiling for nearly every space and stops discriminating.

**The multiplier is clipped to 0.80 to 1.25.** Secondary research can shade the
ranking; it can never overturn what the audit shows.

**Four signals are derived from the supplied dataset rather than published.**
They are labelled `internal://` and marked as derived in every citation, so a
reader can tell them apart from external sources at a glance.

---

## About the agent

**The model never calculates.** Every figure comes from a tool result, and the
numeric guardrail enforces it. This is an architectural constraint, not a
prompt instruction.

**Baseline tool calls run regardless of what the model decides.** The planner
schedules evidence by intent before the model is consulted, which is what makes
the agent gather the right data even when the model chooses badly, and what
makes the no-credentials path work.

**One rewrite on a failed grounding check, then fall back.** If an answer
cannot be grounded in two attempts, the honest outcome is to return the
deterministic rendering rather than keep asking until something slips through.

**Numeric tolerance of 2 per cent, ignoring values below 3.** Rounding in prose
is legitimate; fabrication is not. The floor stops list positions and small
counts generating false positives.

**Scope enforcement is asymmetric.** Topics the dataset cannot contain, such as
share price or clinical advice, refuse unconditionally. Adjacent therapy areas
refuse only when nothing in scope is present, because "how does cardiac compare
with respiratory" is a legitimate framing question. A question with no in-scope
vocabulary at all is refused, because answering it would produce market context
with no bearing on what was asked.
