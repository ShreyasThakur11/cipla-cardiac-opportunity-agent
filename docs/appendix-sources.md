---
title: "Appendix: sources"
layout: default
nav_order: 4
---

# Appendix: sources for external data

The case requires sources for external data in an appendix. This is that
appendix, and it is generated from the same corpus the agent retrieves from, so
it cannot drift from what the agent actually cited.

Regenerate with:

```bash
curl http://localhost:8000/signals/citations        # service running
cardiac-agent export                                # writes analysis_metadata.json
```

Each signal is a markdown file in `data/external/signals/` with structured
front matter. Two are marked **derived**: they are analysis of the supplied
dataset rather than published research, and are labelled as such so a reader
can tell the difference at a glance.

---

## External sources

### [S-01] Hypertension prevalence and the treatment gap in India

- **Publisher:** National Family Health Survey-5 (NFHS-5), Ministry of Health and Family Welfare, Government of India
- **Reference:** NFHS-5 (2019-21), analysed in *Prevalence of Hypertension among Indian Adults Based on Global Standards*
- **URL:** https://www.medrxiv.org/content/10.1101/2025.09.17.25335963v1.full
- **Accessed:** 26 July 2026 · **Confidence:** High
- **Used for:** Age-standardised hypertension prevalence of 22.4 per cent, and the finding that only 40.7 per cent of diagnosed cases are on medication. Supports treating anti-hypertensives as a volume-led rather than saturated category. ICMR's NNMS (2017-18) is cited alongside at 28.5 per cent for the wider 18-69 age band.

### [S-02] The "75/25" national NCD initiative

- **Publisher:** Ministry of Health and Family Welfare, Government of India (Press Information Bureau)
- **Reference:** Update on the 75/25 Initiative; NP-NCD screening campaign via Ayushman Arogya Mandir facilities
- **URL:** https://www.pib.gov.in/PressReleasePage.aspx?PRID=2110390
- **Accessed:** 26 July 2026 · **Confidence:** High
- **Used for:** 42.01 million individuals treated for hypertension as of 5 March 2025 against a 75 million target by December 2025. Supports volume growth while arguing against over-weighting value growth, because public-channel volume typically carries lower realised price.

### [S-03] Lipid Association of India consensus on lipid management

- **Publisher:** Lipid Association of India, *Journal of Clinical Lipidology*
- **Reference:** LAI 2023 update on cardiovascular risk assessment and lipid management in Indian patients, Consensus statement IV
- **URL:** https://www.lipidjournal.com/article/S1933-2874(24)00006-0/fulltext
- **Accessed:** 26 July 2026 · **Confidence:** High
- **Used for:** Ezetimibe positioned first in the escalation sequence after a maximally tolerated statin, with the note that ezetimibe and bempedoic acid are only moderately more expensive than statins. The strongest single external tailwind in the corpus and the clinical basis for the ezetimibe recommendation.

### [S-04] Air pollution and cardiovascular mortality in India

- **Publisher:** *The Lancet Planetary Health*; Harvard T.H. Chan School of Public Health
- **Reference:** *Estimating the effect of annual PM2.5 exposure on mortality in India: a difference-in-differences approach*
- **URL:** https://www.thelancet.com/journals/lanplh/article/PIIS2542-5196(24)00248-1/fulltext
- **Accessed:** 26 July 2026 · **Confidence:** Medium
- **Used for:** Approximately 1.5 million additional deaths per year associated with air pollution, roughly half attributable to cardiovascular effects, with ischaemic heart disease around 47 per cent of PM2.5-attributable deaths in major Indian cities. Addresses the case's environmental-shift prompt. Deliberately given low magnitude: the epidemiology is strong but the translation into a specific molecule class over five years is indirect.

### [S-05] Inclisiran launch in India

- **Publisher:** Novartis; reported by ChemXpert and Indian business press
- **Reference:** Sybrava (inclisiran) launched January 2024; marketing partnerships with Mankind Pharma (Crenzlo), JB Pharma (Izirize) and Lupin (Tilpazan)
- **URL:** https://chemxpert.com/blog/how-novartis-is-redefining-drug-pricing-in-india-with-inclisiran
- **Accessed:** 26 July 2026 · **Confidence:** Medium
- **Used for:** Premium-priced innovator entry at roughly ₹120,000 per injection, reaching approximately ₹7.7 crore across three partners in the year from April 2024. Evidence that the realistic route into premium lipid innovation in India is in-licensing rather than independent launch.

### [S-06] Saroglitazar as an originator-controlled NCE

- **Publisher:** Zydus Lifesciences; New Drug Approvals; Zydus Healthcare
- **Reference:** Saroglitazar (Lipaglyn) launched in India September 2013, the first new chemical entity developed by an Indian pharmaceutical company
- **URL:** https://www.zydushealthcare.com/brand/lipaglyn/
- **Accessed:** 26 July 2026 · **Confidence:** High
- **Used for:** Explaining why the fastest-growing lipid sub-segment is not an accessible opportunity. Patent status was not verified and freedom to operate would require legal review, which the analysis states explicitly rather than assuming.

### [S-07] NLEM 2022 and price control

- **Publisher:** Ministry of Health and Family Welfare; National Pharmaceutical Pricing Authority
- **Reference:** National List of Essential Medicines 2022; ceiling prices administered under the Drug Price Control Order
- **URL:** https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadConsumer/nlem2022.pdf
- **Accessed:** 26 July 2026 · **Confidence:** High
- **Used for:** 384 medicines across 27 therapeutic categories subject to NPPA ceiling prices. The regulatory basis for weighting constant-price and volume growth above reported value, and for treating price erosion as a negative in the competitive-headroom pillar.

### [S-08] Indian hypertension guidance on combination therapy

- **Publisher:** Indian Society of Hypertension (InSH), *Hypertension Journal*
- **Reference:** InSH Consensus Guideline for the Management of Hypertension, 2025
- **URL:** https://9vom.in/journals/index.php/htnj/article/download/1097/909/3409
- **Accessed:** 26 July 2026 · **Confidence:** Medium
- **Used for:** The clinical mechanism behind fixed-dose combinations outgrowing the plain molecules they are built from. Confidence is medium because the guideline is recent and Indian prescribing adopts guidance with a lag; the dataset evidence for the shift is stronger than the citation alone.

### [S-09] Cardiovascular disease burden in India

- **Publisher:** Peer-reviewed literature on India's non-communicable disease burden
- **Reference:** Cardiovascular disease accounted for approximately 14.1 per cent of disability-adjusted life years in India in 2016
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC10042544/
- **Accessed:** 26 July 2026 · **Confidence:** Medium
- **Used for:** The evidence base for the assumption that the Cardiac therapy area continues to grow ahead of the overall pharmaceutical market. Applies uniformly to all three segments, so its net effect on relative prioritisation is close to zero by construction.

### [S-10] Bempedoic acid and non-statin escalation

- **Publisher:** Korean Society of Lipid and Atherosclerosis; Esperion Therapeutics
- **Reference:** 2024 KSoLA update on new lipid-lowering agents: inclisiran and bempedoic acid; bempedoic acid approved in the US as Nexletol and, with ezetimibe, as Nexlizet
- **URL:** https://e-jla.org/DOIx.php?id=10.12997%2Fjla.2025.14.2.135
- **Accessed:** 26 July 2026 · **Confidence:** Medium
- **Used for:** Reinforcing the shift toward non-statin add-on therapy in the statin-intolerant population. Combined with [S-03] under the linker's within-category damping so that two sources describing one trend cannot double count.

---

## Derived from the supplied dataset

These are not external publications. They are analysis of the case dataset,
included in the corpus so the agent can cite the reasoning behind a structural
claim, and labelled so a reader can tell them apart from published sources.

### [S-11] The cilnidipine franchise spans several sub-segments

- **Source:** Internal analysis of the Ascend Season 4 Cardiac dataset, MAT February 2026
- **Used for:** Establishing that the cilnidipine franchise is visible only when packs are summed across the reporting hierarchy, and that the plain molecule is concentrated while the combinations are not. This is the evidence behind the anchor-molecule space level.

### [S-12] Legacy anti-hypertensive classes are in real decline

- **Source:** Internal analysis, MAT February 2024 to MAT February 2026
- **Used for:** Identifying spaces where reported value growth is positive while constant-price and volume growth are negative. Applies the organisers' own guidance that MAT CP measures real demand and QTY reflects consumption.

### [S-13] Cipla's strategic starting position

- **Source:** Cipla corporate description in the case brief, combined with share and growth from the dataset
- **Used for:** Grounding statements about Cipla's stated strategy of deepening its position where it has a clear and sustainable right to win. Carries zero magnitude: it shapes interpretation, not the numbers.

### [S-14] Metric definitions

- **Source:** Glossary worksheet supplied with the Cardiac dataset
- **Used for:** The definitions of MAT, MAT CP, QTY MAT and PR, and the organisers' guidance that MAT CP should be used to understand real demand growth while QTY reflects actual consumption. The methodological backbone of the entire framework, and the citation used whenever the agent explains why it discounted a space whose headline growth looked strong.

---

## How signals influence the analysis

Stated here so the mechanism can be challenged.

1. Each signal declares a direction (tailwind, headwind or neutral), a
   magnitude, and a confidence level in its front matter.
2. Confidence discounts magnitude: high counts in full, medium at 60 per cent,
   low at 30 per cent.
3. Within a category the strongest signal counts fully and the rest at half
   weight, so two guideline documents describing one clinical shift reinforce
   rather than compound.
4. The resulting tilt is **centred on the median tilt of its space level**. A
   signal that applies to every space therefore moves nothing, which is the
   honest treatment: it is context for the therapy area, not a reason to prefer
   one space over another. Only differential evidence changes the ranking.
5. The result is clipped to a band of 0.80 to 1.25 and applied to one metric
   within the future-potential pillar, which carries 40 per cent of the Market
   Opportunity Index. External research can therefore shade the ranking by a
   bounded amount; it can never overturn what the audit shows.

Every signal attached to every space, with the reason it matched and its
numeric contribution, is recorded in the agent's trace and returned by
`space_deep_dive` under `external_signals.links`.
