---
title: Limitations
layout: default
nav_order: 13
---

# Limitations

What this system cannot tell you. Stated plainly, because a recommendation is
only as good as the reader's understanding of what sits behind it.

---

## The data

**Two annual observations.** MAT February 2024, 2025 and 2026 give two
year-on-year comparisons. That supports a direction. It does not support a
cycle, a seasonal decomposition, or a confidence interval on a growth rate. The
three supplied months help at the margin, but three months is a momentum
signal, not a time series.

Consequence: every five-year projection is a structured extrapolation with an
explicit mean-reversion assumption, not a forecast in the statistical sense.
The agent is instructed to present them that way, and each projection returns
its assumptions alongside the number.

**Retail audit only.** Institutional, hospital and government-tender channels
are absent. This matters more here than it would in most therapy areas: India's
"75/25" programme has put tens of millions of patients on hypertension therapy
through public primary care, and none of that volume appears in this dataset.
A space that looks small in retail may be materially larger in total.

**One geography.** India. Nothing here transfers to Cipla's other markets.

**No patent, exclusivity or regulatory status.** The single largest gap for the
question being asked. The analysis can identify that a space is
originator-dominated by its competitive structure, and does so for saroglitazar
and inclisiran. It cannot tell you whether Cipla could legally enter, when
exclusivity expires, or what a filing would require. Any entry recommendation
needs a freedom-to-operate review that is outside this dataset.

**No cost, margin, or price-point data beyond price to retailer.** Every
conclusion is about revenue opportunity. Whether a space is profitable to enter,
what gross margin it carries, and what the promotional cost of a point of share
would be are all unanswerable here.

**No promotional or field-force data.** Right to win is measured through
observable proxies: molecule adjacency, brand franchise, sub-segment presence.
Actual detailing capacity, prescriber coverage and share of voice are not in
the data. A space where the analysis says Cipla has a route in may still be
unwinnable if the field-force economics do not work.

**No prescriber, patient or epidemiological granularity.** The audit is
commercial. Which specialties prescribe what, adherence, switching behaviour
and treatment-line position are all inferred from combination structure rather
than observed.

**Zero-value rows.** Roughly 1,300 packs report zero in the latest MAT. They
are retained because they are real discontinuations or pre-launch entries, and
they are correctly excluded from player counts. They do inflate the SKU count
in any raw row-count query.

---

## The framework

**Weights are judgement, not derived.** There is no labelled outcome to
optimise against, so no weight in `config/settings.yaml` is empirically
validated. The sensitivity analysis exists to bound this: it shows which
conclusions survive plausible re-weightings and which do not, and the agent is
required to report that honestly. But a robustness measure is not the same as
a correctness measure.

**Percentile normalisation loses magnitude.** A space at the 90th percentile on
growth might be growing at 20 per cent or 80 per cent depending on the
distribution. The raw values are always shown alongside the scores, but the
score itself is a rank.

**The size floor is consequential.** Excluding spaces below ₹100 crore removes
213 of 321 constructed spaces. Emerging molecules that will matter in five
years but are small today are filtered out. Rosuvastatin + Ezetimibe at ₹183
crore only just clears it; at last year's ₹98 crore it would not have.

**Anchor-molecule spaces overlap.** They are not additive, and summing them
double counts. Every output that shows them says so, but a reader taking a
number out of context could get this wrong.

**Growth clipping is visible in the output.** Rates are clipped to
`[-100%, +300%]`. Where a Cipla position grew from a near-zero base the reported
growth may be the clip rather than the true rate. It is bounded and conservative
in the direction that matters, but a figure of exactly 300 per cent should be
read as "very large" rather than as a measurement.

---

## The external signals

**Curated, not systematic.** Fourteen documents chosen for relevance. Not a
literature review, not exhaustive, and not free of selection bias. Their
influence is bounded to a 0.80 to 1.25 multiplier on one metric within one
pillar for exactly this reason.

**Access-date sensitive.** Every signal carries an access date of 26 July 2026.
Guidelines, pricing decisions and approvals change. A signal that was accurate
then may not be at presentation time.

**Signal magnitudes are assigned by judgement.** Nothing calibrates "this
guideline is worth 0.18 and this environmental evidence is worth 0.06". They
are ordered sensibly, and the centring and clipping bound the damage, but they
are not measurements.

**Linking is keyword and taxonomy based.** A signal attaches to a space by
molecule, sub-segment, segment or keyword match. It can over-attach, and one
did during development: a cilnidipine signal originally listed sub-segments and
tilted every dual combination in the market, including those with no
cilnidipine in them. That was caught and narrowed to molecule scope. Others may
remain.

**Four signals are derived from the dataset, not published.** They are labelled
as such, but a reader skimming citations could mistake them for independent
corroboration. They are not: they are the same evidence, restated.

---

## The agent

**Numeric grounding checks presence, not correctness of use.** The verifier
confirms every number in the answer appears in the evidence. It cannot detect a
number correctly quoted but attributed to the wrong space, or a real figure
used to support a conclusion it does not support. That failure mode requires
human review.

**Citation checking is heuristic on the claim side.** Unresolvable citations
are caught reliably. Detecting an *unsourced* external claim relies on phrase
markers, which will miss a claim phrased unusually and flag some
dataset-derived sentences as needing a source.

**Intent classification is pattern based.** Ten regular expressions route a
question to a baseline evidence plan. A question phrased outside those patterns
falls back to a general plan, and with a model available the model compensates
by calling more tools. Without one, an unusual question gets a thinner answer.

**Scope control errs towards refusal.** A question with no in-scope vocabulary
is refused even if it could have been answered. This is deliberate, and it does
mean an unusually phrased legitimate question can be turned away.

**The deterministic renderer is template-based.** It produces the same numbers
as the model path but cannot synthesise across evidence blocks, weigh a novel
trade-off, or answer a question shape it has no template for. It is a floor on
quality, not a substitute for the model.

**Model behaviour is not fully deterministic.** With a provider configured, the
same question can produce differently worded answers. The numbers cannot vary,
because they are verified against the evidence, but the emphasis can. The
evaluation suite runs in deterministic mode for this reason.

---

## What would change the conclusions

Honest answer to "how confident should I be".

| If this were true | The conclusions that would change |
| --- | --- |
| Cilnidipine combinations face a patent barrier | Priority 2 becomes uninvestable; the answer collapses to the lipid recommendations |
| The ezetimibe space consolidates in the next 12 months | Priority 1's window closes; it becomes a build rather than an extension |
| Public-channel volume is much larger than retail suggests | Plain molecules and first-line therapies gain against premium combinations |
| Field-force cost per share point is prohibitive | The cilnidipine build fails on economics even though the market analysis holds |
| Price ceilings are extended to combinations | The entire combination thesis weakens, since much of its value premium is price |
| A longer history shows 2025-26 was anomalous | The growth ranking changes materially; two observations cannot detect this |

The first two are the ones to check before acting.
