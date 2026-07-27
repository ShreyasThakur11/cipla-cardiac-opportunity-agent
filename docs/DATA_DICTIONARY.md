---
title: Data dictionary
layout: default
nav_order: 11
---

# Data dictionary

---

## Source workbook

Two worksheets. `Cardiac` carries 7,452 rows and 36 columns, one row per pack.
`Glossary` carries the organisers' metric definitions.

### Identification

| Column | Type | Notes |
| --- | --- | --- |
| `KEY(MS+SG+FINAL NFC)` | text | Composite key: molecule, subgroup, formulation. 248 distinct. |
| `PACK_DESC` | text | Pack description including strength and count. 7,438 distinct. |
| `BRANDS` | text | Brand name. 3,788 distinct. |
| `MOLECULE_DESC` | text | Active ingredients, `+` separated. 285 distinct. |
| `STRENGTH (ONLY 1 MOL.)` | text | Strength of the first molecule only. |
| `PACK VOLUME` | text | Populated for liquids and injectables; `0` for solids. |

### Company

| Column | Type | Notes |
| --- | --- | --- |
| `COMPANY` | text | Consolidated group; trailing `*` marks consolidation. 279 distinct. |
| `MANUFACT. DESC` | text | Manufacturing entity. |
| `COMPANY CLUSTER`, `COMPANY DIVISION`, `COMPANY SUB DIVISION` | text | Reporting hierarchy, near-identical to COMPANY in this extract. |
| `COMPANY India Business Prescription` | text | Business unit, e.g. `CIPLA IB RX`. |
| `INDIAN_MNC` | text | `INDIAN` or `MNC`. 256 of 7,452 rows are MNC. |

### Classification

| Column | Type | Notes |
| --- | --- | --- |
| `SUPERGROUP` | text | `CARDIAC` throughout. |
| `GROUP` | text | ATC-4 class, e.g. `C02F HYPOTENSIVE DUAL COMB.`. 14 distinct. |
| `SUBGROUP` | text | ATC-5 molecule or combination. 149 distinct. |
| `CARDIAC SEGMENT` | text | Anti Hypertensives, Lipid Regulators, Anti Angina. |
| `CARDIAC SUB SEGMENTS` | text | 15 values including one placeholder `-`. |
| `ACUTE_CHRONIC` | text | `CHRONIC` throughout. |
| `FINAL NFC` | text | Dosage form. SOLIDS 7,390; INJECTIONS 43; PAEDIA 8; LIQUIDS 5; TOPICAL 5; OPHTHAL 1. |
| `Plain/Combination` | text | Combination 4,547; Plain 2,905. |

### Measures

All numeric, in INR crore for value and pack-dependent units for quantity.

| Column | Meaning |
| --- | --- |
| `MAT FEB'24` / `'25` / `'26` | Moving annual total value. MAT Feb'26 covers March 2025 to February 2026. |
| `MAT CP FEB'24` / `'25` / `'26` | Moving annual total at constant prices, stated at the previous year's price level. |
| `QTY MAT FEB'24` / `'25` / `'26` | Moving annual total quantity. |
| `Sales 'DEC'25`, `'JAN'26`, `'FEB'26` | Individual month value. |
| `PR_DEC'25`, `PR_JAN'26`, `PR_FEB'26` | Price to retailer. |

### How the organisers say to read them

From the glossary, and the basis for the framework's weighting:

- MAT represents overall market size and long-term growth.
- **MAT CP should be used to understand real demand growth, excluding price effects.**
- **QTY reflects actual consumption trends.**
- PR and monthly sales can be used to assess recent pricing and momentum.

---

## Derived fields

Added by `ingestion/normalize.py`.

| Field | Type | Derivation |
| --- | --- | --- |
| `company_clean` | text | COMPANY with the trailing `*` removed. |
| `is_focal` | bool | COMPANY equals `market.focal_company`. |
| `molecules` | list | MOLECULE_DESC split on `+`, salt suffixes stripped. |
| `molecule_count` | int | Length of `molecules`. |
| `molecule_canonical` | text | Canonical molecules rejoined with ` + `. |
| `molecule_signature` | text | Same, sorted, so `A + B` and `B + A` match. |
| `treatment_archetype` | text | Monotherapy, Dual FDC, or Triple / Poly FDC. |
| `brand_root` | text | Umbrella brand recovered from a line extension. |
| `brand_key` | text | `company_clean | brand_root`. |
| `realised_price_per_unit` | float | MAT Feb'26 over QTY MAT Feb'26, guarded. |
| `is_oral_solid` | bool | FINAL NFC equals SOLIDS. |
| `is_mnc` | bool | INDIAN_MNC equals MNC. |

---

## Warehouse tables

Written to `data/processed/cardiac.duckdb`, with a parquet mirror alongside.

### `sku_facts`

One row per pack: every source column plus every derived field. 7,452 rows.

### `space_facts`

One row per opportunity space. 326 rows before filtering, 108 after.

| Column | Meaning |
| --- | --- |
| `level` | One of the six space levels. |
| `space_id` | Stable identifier, e.g. `MOL_C02F0O_CILNIDIPINE_TELMISARTAN`. |
| `space_label` | Human-readable label. |
| `segment`, `sub_segment` | Dominant context by value. |
| `value_t0/t1/t2` | Summed MAT for the three periods. |
| `cp_t0/t1/t2` | Summed MAT CP. |
| `qty_t0/t1/t2` | Summed QTY MAT. |
| `recent_3m_sales` | Sum of the three monthly columns. |
| `focal_value_t0/t1/t2` | Cipla's value in the space. |
| `sku_count` | Distinct packs. |

### `space_membership`

The SKU-to-space map, one row per pair. 50,191 rows. Retained so competitive
structure and Cipla's position can be recomputed for any subset without
re-deriving the hierarchy.

### `company_facts` and `brand_facts`

Value by company, and by brand, within every space, with share and rank.

### `glossary` and `build_metadata`

The organisers' definitions, and the build record including a SHA-256 of the
source workbook.

---

## Computed metrics

Added by the analytics package, present on every scored space.

### Growth and demand

| Metric | Formula |
| --- | --- |
| `value_yoy` | `value_t2 / value_t1 - 1` |
| `value_cagr_2y` | `(value_t2 / value_t0) ^ 0.5 - 1` |
| `absolute_growth_cr` | `value_t2 - value_t1` |
| `real_growth` | `cp_t2 / value_t1 - 1` |
| `volume_growth` | `qty_t2 / qty_t1 - 1` |
| `price_effect` | `value_yoy - real_growth` |
| `momentum` | `(recent_3m_sales x 4) / value_t2 - 1` |
| `price_per_unit_t2` | `value_t2 / qty_t2` |

Rates are clipped to `[-1.0, 3.0]`; momentum to `[-0.9, 1.5]`.

### Competition

| Metric | Meaning |
| --- | --- |
| `hhi` | Sum of squared percentage shares. |
| `n_players` | Companies with value above zero. |
| `leader_share`, `top3_share`, `top5_share` | Concentration at the top. |
| `leader_company` | Largest company by value. |
| `effective_competitors` | `10000 / hhi`. |
| `crowding` | Players per ₹100 crore. |
| `share_churn` | Half the total absolute share movement year on year. |
| `new_entrant_count` | Companies with zero in t1 and value in t2. |
| `price_erosion` | `max(0, -price_effect)`. |
| `concentration_label` | Fragmented, Moderately concentrated, Concentrated. |
| `is_structurally_closed` | Fewer than 3 players, or leader above 80 per cent. |

### Focal position and right to win

| Metric | Meaning |
| --- | --- |
| `focal_share_t2` | Cipla's share of the space. |
| `focal_share_delta_pp` | Share change in percentage points. |
| `focal_growth_gap` | Cipla's growth minus the space's growth. |
| `rtw_current_share` | Same as `focal_share_t2`. |
| `rtw_share_momentum` | `focal_growth_gap`, clipped to `[-0.5, 0.5]`. |
| `rtw_molecule_adjacency` | Value-weighted share of the space's molecules Cipla markets. |
| `rtw_brand_franchise` | 1.0 molecule match, 0.75 ATC-5, 0.60 sub-segment, 0.30 segment, else 0. |
| `rtw_detailing_adjacency` | Cipla's share of the parent sub-segment. |
| `rtw_formulation_fit` | Dosage-form mix overlap with Cipla's cardiac mix. |
| `adjacent_cipla_brands` | Extendable brand roots already carrying one of the space's molecules. |

### Signals and scores

| Metric | Meaning |
| --- | --- |
| `trend_tilt_raw` | Summed signed magnitudes before centring. |
| `trend_multiplier` | Centred within level, clipped to `[0.80, 1.25]`. |
| `trend_signal_ids` | Comma-separated signal identifiers that attached. |
| `pillar__*` | The four pillar scores, 0 to 100. |
| `score__pillar__metric` | Every metric percentile, retained for explanation. |
| `market_opportunity_index` | Weighted blend of the first three pillars. |
| `right_to_win_score` | The fourth pillar. |
| `rtw_gate` | The multiplier derived from it. |
| `cipla_priority_score` | `MOI x rtw_gate`. |
| `moi_rank`, `cps_rank` | Rank within level. |
| `moi_band`, `rtw_band` | High / Medium / Low and Strong / Moderate / Weak. |
| `strategic_verdict` | Double down, Build capability, Selective participation, Avoid or partner, Harvest or exit. |

---

## Space levels

| Level | Prefix | Built from | Scored |
| --- | --- | --- | ---: |
| `segment` | `SEG_` | CARDIAC SEGMENT | 3 |
| `sub_segment` | `SUB_` | Segment and sub-segment | 14 |
| `molecule_class` | `CLS_` | GROUP (ATC-4) | 13 |
| `molecule_combination` | `MOL_` | SUBGROUP (ATC-5) | 45 |
| `treatment_archetype` | `ARC_` | Segment and archetype | 7 |
| `anchor_molecule` | `ANC_` | Every pack containing an ingredient | 26 |

Anchor spaces overlap the others and are not additive with them.
