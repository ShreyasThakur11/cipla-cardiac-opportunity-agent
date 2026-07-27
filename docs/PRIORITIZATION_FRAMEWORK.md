---
title: Prioritisation framework
layout: default
nav_order: 5
---

# The prioritisation framework

Every number in this document lives in `config/settings.yaml`. Nothing here is
hard-coded in Python, so a challenge to any assumption is answered by editing
one value and re-running.

---

## Two scores, not one

The case asks two questions that a single blended score would quietly merge:

> What are the Top 3-5 opportunities identified by the AI agent, **and** which
> 2-3 should Cipla actively prioritise?

So the framework produces two numbers.

**Market Opportunity Index (MOI)** rates a space for anybody. Cipla does not
appear in it.

```
MOI = 0.34 x market_attractiveness
    + 0.40 x future_potential
    + 0.26 x competitive_headroom
```

**Cipla Priority Score (CPS)** is that index passed through a right-to-win
gate.

```
CPS = MOI x gate(right_to_win)
```

A space with a high MOI and a low CPS is not an oversight. It is a real
opportunity that somebody else is positioned to win, and the agent is
instructed to name those explicitly. Other Lipid Reducers is the clearest case
in this dataset: sixth on attractiveness, and a "harvest or exit" verdict once
right to win is applied.

---

## Pillar 1: Market attractiveness (34 per cent of MOI)

Is the space worth anybody's attention today?

| Metric | Weight | Source | Reasoning |
| --- | ---: | --- | --- |
| Size | 45% | MAT Feb'26 | A win in a ₹4,000 crore space moves a company; a win in a ₹40 crore space does not. |
| Absolute value added | 35% | MAT Feb'26 minus MAT Feb'25 | Percentage growth flatters small bases. Crore added is what a portfolio manager actually competes for. |
| Two-year CAGR | 20% | MAT Feb'26 over MAT Feb'24 | Smooths a single anomalous year. |

Size and absolute growth are weighted together at 80 per cent deliberately.
Percentage growth alone would put a ₹20 crore molecule that doubled above a
₹4,000 crore sub-segment that added ₹600 crore, which is not how a portfolio
decision is taken.

---

## Pillar 2: Future potential (40 per cent of MOI)

Will it still be growing in five years? The heaviest pillar, because the case
asks which spaces will outperform "over the next 3-5 years".

| Metric | Weight | Source | Reasoning |
| --- | ---: | --- | --- |
| Real growth | 30% | MAT CP Feb'26 against MAT Feb'25 | The organisers' glossary states MAT CP holds prices at the prior year's level, so its growth is demand growth. This is the single most informative metric in the dataset. |
| Volume growth | 25% | QTY MAT Feb'26 against Feb'25 | Independent confirmation of the constant-price read. Catches a space growing on trade loading rather than prescriptions. |
| Momentum | 20% | Dec'25 + Jan'26 + Feb'26 annualised, against MAT | The earliest available signal that a trend is bending. It is why the dataset ships three separate months. |
| External trend | 25% | RAG-derived multiplier | Guidelines, epidemiology, regulation and innovation, bounded and cited. |

Reported value growth carries **no weight at all** in this pillar. It appears in
market attractiveness, where it belongs as a measure of today. Price gains do
not compound the way prescription volume does, and a material part of India's
essential cardiovascular basket sits under administered ceiling prices, so
price-led growth is structurally fragile.

**Price effect** is reported as the residual, `reported growth − real growth`,
and surfaced on every space card. A space growing 12 per cent on value and one
per cent on volume is a price story, and the agent is instructed to say so.

### How the external multiplier is computed

1. Each signal declares direction, magnitude and confidence in its front
   matter.
2. Confidence discounts magnitude: high 1.0, medium 0.6, low 0.3.
3. Within a category the strongest signal counts fully and the rest at half
   weight, so two guideline documents describing one clinical shift reinforce
   without compounding.
4. The tilt is **centred on the median tilt of its space level**.
5. The result is clipped to `[0.80, 1.25]`.

Step four is what makes the mechanism work. Several signals apply to nearly
every space in the market. Left uncorrected they add the same constant
everywhere and push every multiplier into the ceiling, turning a discriminating
input into a flat one. Centred, a signal that applies to everything moves
nothing, which is the honest treatment: it is context for the therapy area, not
a reason to prefer one space over another.

Step five bounds the whole mechanism. Secondary research can shade the ranking;
it can never overturn what the audit shows. If a space looks good only because
of a published paper, that is a finding about the paper.

---

## Pillar 3: Competitive headroom (26 per cent of MOI)

Can anyone new take share? All four metrics are inverted, so a lower raw value
scores higher.

| Metric | Weight | Reasoning |
| --- | ---: | --- |
| HHI | 35% | Standard concentration measure. Above 2,500 is concentrated. |
| Leader share | 25% | One player at 60 per cent is harder to displace than three at 20 per cent each, despite the same combined share. |
| Crowding | 15% | Players per ₹100 crore. A fragmented space with ninety entrants is not open, it is commoditised. |
| Price erosion | 25% | Negative price effect, floored at zero. Value being destroyed rather than created. |

Two structural filters run before scoring. Spaces below **₹100 crore** are
excluded, because a win there cannot move a company of Cipla's size and small
bases produce unstable percentages. Spaces with fewer than **three active
players** are excluded as structurally closed. 213 of the 321 constructed
spaces are filtered out, leaving 108 scored.

Share churn and new-entrant count are computed and reported on every space card
but carry no weight, because they are informative for a human reading the card
and too noisy over two annual observations to drive a ranking.

---

## Pillar 4: Right to win (the gate)

This pillar does not enter the MOI. It becomes a multiplier.

| Component | Weight | What it measures |
| --- | ---: | --- |
| Current share | 22% | Where Cipla stands today. |
| Share momentum | 22% | Cipla's growth minus the space's growth. |
| Molecule adjacency | 20% | Value-weighted share of the space's active ingredients Cipla already markets anywhere in Cardiac. |
| Brand franchise | 18% | Whether an umbrella brand can be extended. 1.0 if a Cipla brand already carries one of the space's molecules, 0.75 for the same ATC-5, 0.60 for the same sub-segment, 0.30 for the same segment. |
| Detailing adjacency | 10% | Cipla's share of the parent sub-segment, as a proxy for whether the field force already calls on those prescribers. |
| Formulation fit | 8% | Overlap between the space's dosage-form mix and Cipla's cardiac mix. |

Current share and share momentum are weighted equally on purpose. Direction
matters as much as position for a company at 1.68 per cent therapy share:
3 per cent and gaining beats 8 per cent and bleeding.

Molecule adjacency and brand franchise together carry 38 per cent because they
are the cheapest advantages available. Where Cipla already sells the molecule
or owns a brand prescribers recognise, entering an adjacent space costs a
fraction of a standing start, and both are directly observable in the audit
rather than asserted.

### The gate curve

```
gate(rtw) = 0.35 + 0.65 x (rtw / 100) ^ 1.35
```

| Right to win | Multiplier |
| ---: | ---: |
| 0 | 0.35 |
| 25 | 0.45 |
| 50 | 0.60 |
| 75 | 0.79 |
| 100 | 1.00 |

The exponent above 1.0 makes weak right to win hurt more than linearly. In a
market where Cipla holds 1.68 per cent overall, the failure mode to guard
against is chasing growth into spaces with no structural advantage. The floor
of 0.35 stops the gate from zeroing out a space entirely, because a space Cipla
cannot win today may still be worth watching.

---

## Normalisation

Percentile rank, computed **within a space level**, after winsorising at the
2nd and 98th percentiles.

**Why percentile rather than min-max.** Pharmaceutical audit data is heavily
skewed. A handful of molecules carry most of the value, and min-max would push
everything else into the bottom decile of the scale. Percentile rank is
monotone-invariant, so it needs no log transform and no distributional
assumption.

**Why within a level.** Comparing three segments against a hundred and fifty
molecules on a common scale would say more about the size of the list than
about the market. Each level is ranked against its own peers, and ranks are
reported per level.

**Why winsorise.** One pack that grew from ₹0.001 crore to ₹5 crore should not
compress every other space's growth percentile. Growth rates are separately
clipped to `[-100%, +300%]` at the metric layer for the same reason.

---

## Strategic verdict

The two-axis view produces the sentence the case asks for. Bands are 70 for
high and 45 for medium.

| | Right to win strong | Moderate | Weak |
| --- | --- | --- | --- |
| **Opportunity high** | Double down | Build capability | Avoid or partner |
| **Medium** | Selective participation | Selective participation | Harvest or exit |
| **Low** | Harvest or exit | Harvest or exit | Harvest or exit |

---

## Forecasting

The case asks which spaces outperform over three to five years. Two years of
history is not much to forecast from, so the method is explicit rather than
hidden.

**Base rate**, weighted towards demand:

```
rate = 0.40 x real_growth + 0.30 x volume_growth
     + 0.20 x value_cagr_2y + 0.10 x momentum
```

**External tilt**: multiply by the space's `trend_multiplier`.

**Mean reversion**: the excess over the therapy-area rate decays 28 per cent a
year. Nothing grows at 45 per cent for five years, and assuming it does is how
forecasts produce indefensible numbers.

**Caps**: the starting rate is bounded to `[-15%, +45%]`.

**Scenarios**: bull and bear shift the starting rate by 4 percentage points.

Every projection returns its assumptions alongside the number. These are
structured extrapolations, not plans, and the agent is instructed to present
them as such.

---

## Sensitivity

Any scoring framework can be accused of engineering its own conclusion. The
honest response is to show what happens when the weights move.

Every weight block is redrawn from a Dirichlet distribution centred on the
configured values, with concentration 40 (higher is tighter), and the market
re-scored 500 times from a fixed seed. The reported statistic is how often each
space stays in the top K.

| Frequency | Interpretation |
| ---: | --- |
| Above 0.80 | Robust to how the framework is weighted |
| 0.60 to 0.80 | Sensitive; state the dependency |
| Below 0.60 | A judgement call, and must be presented as one |

The agent is required to run this before presenting a final recommendation and
to report the result honestly, including when it undermines a ranking.

---

## Changing the framework

```yaml
# config/settings.yaml
scoring:
  moi_weights:
    market_attractiveness: 0.25   # was 0.34
    future_potential: 0.50        # was 0.40
    competitive_headroom: 0.25    # was 0.26
```

Then `cardiac-agent rank --level sub_segment`. Every weight block is validated
to sum to 1.0 and the run fails loudly if it does not. The full weight set used
is attached to every `ScoreResult` and written into `cardiac-agent export`, so
a reader can always tell which framework produced a given number.
