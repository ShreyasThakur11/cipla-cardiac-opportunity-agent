---
title: Future improvements
layout: default
nav_order: 18
---

# Future improvements

Ordered by how much they would change an answer, not by how interesting they
are to build.

---

## Would change the conclusions

### Patent and exclusivity status

The largest gap in the analysis. The system can identify that a space is
originator-dominated from its competitive structure, and does so for
saroglitazar and inclisiran. It cannot say whether entry is legally possible or
when exclusivity ends.

Every entry recommendation currently carries a caveat that a freedom-to-operate
review is needed. Removing that caveat would require joining an IP dataset on
molecule and geography and adding an eligibility gate ahead of the right-to-win
pillar, so a blocked space is excluded rather than ranked low.

Highest value, and the only item here that would change a recommendation rather
than sharpen one.

### Longer history

Two annual observations support a direction and nothing more. Four or five
years of MAT would allow a real trend decomposition, a variance estimate on
each growth rate, and detection of whether 2025-26 was anomalous. It would also
let the mean-reversion rate be estimated from the data rather than assumed.

The forecast module is written so the base-rate weights and decay parameter are
configuration, which is where they would be replaced.

### Institutional and tender channel data

The dataset is retail only. India's public screening programme has put tens of
millions of patients on hypertension therapy through primary care, none of it
visible here. A space that looks small in retail may be materially larger in
total, and the current analysis would systematically understate first-line
therapies against premium combinations.

### Cost and margin

Every conclusion is about revenue opportunity. Adding transfer price, gross
margin and an estimate of promotional cost per share point would turn "this
space is attractive" into "this space is attractive and worth funding", which
is the question a commercial leader actually asks.

---

## Would sharpen the analysis

### Field-force modelling

Right to win currently uses observable proxies: molecule adjacency, brand
franchise, sub-segment presence. Actual detailing capacity, prescriber
coverage and share of voice would make the pillar considerably stronger, and
would let the system say how much investment a share target implies rather than
only whether a route exists.

### Geographic and specialty granularity

State-level or specialty-level splits would show where a national opportunity
concentrates. Hypertension prevalence ranges from roughly 15 per cent to over
40 per cent across Indian states, so a national average conceals a lot.

### Brand-level right to win

Adjacency is measured at molecule and umbrella-brand level. Modelling
prescriber overlap between specific brands would distinguish a genuine
extension from a nominal one.

### Scenario modelling on the framework itself

The sensitivity analysis perturbs weights. A useful extension would perturb the
*inputs*: what if volume growth in a space were half what is reported, or the
leader defended aggressively on price. That moves the question from "is the
ranking robust to my weights" to "is the recommendation robust to the world
behaving differently".

---

## Would strengthen the system

### Systematic signal curation

Fourteen documents chosen for relevance is curation, not a literature review.
A defined search protocol, inclusion criteria and a refresh schedule would make
the corpus defensible as evidence rather than as illustration. Signal
magnitudes are currently assigned by judgement and would benefit from a stated
rubric.

### A dense retrieval backend

Not needed at fourteen documents, and the interface already accepts one through
`SignalRetriever.register_dense_ranker`. Worth adding if the corpus grows past
roughly a hundred documents, at which point lexical retrieval starts missing
paraphrases.

### Claim-level verification

Numeric grounding checks that every number appears in the evidence. It cannot
detect a real number attached to the wrong space, or a correct figure used to
support a conclusion it does not support. Verifying claim triples, of the form
(space, metric, value), against the evidence would close that gap and is the
most valuable remaining guardrail.

### Multi-turn analytical sessions

Conversation memory currently stores intent and which spaces were discussed,
deliberately excluding figures so a number cannot survive past the guardrail
that checked it. A richer session model would let a user refine a shortlist
across several turns, which is how this analysis would actually be used.

### Automated regression on the scorecard

The test suite verifies the framework computes what it says it computes. A
snapshot test on the full scorecard would catch an unintended ranking change
from an unrelated edit, which is the failure mode most likely to go unnoticed.

---

## Deliberately not planned

**A larger model, or fine-tuning.** The model does not produce numbers, so a
better model produces better prose and nothing else. The constraint on answer
quality is the data, not the language model.

**More space levels.** Six already produce 326 spaces, of which 108 survive
filtering. More levels would add combinatorial noise rather than insight.

**A general-purpose pharmaceutical analytics platform.** This is built for one
dataset, one therapy area and one set of questions. That focus is why the tools
can return interpreted metrics rather than raw rows, and why the numeric
guardrail is enforceable at all. Generalising it would cost both.

**An LLM-as-judge evaluation.** Cheap to produce and impossible to defend when
asked how the judge was validated. Every current metric is a deterministic
assertion, and that property is worth more than the additional coverage.
