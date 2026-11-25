# Power BI report: data model and specification

The SQL layer (`sql/`, built by `python scripts/run_pipeline.py bi`) exports a small star
schema to `reports/bi/`. This page describes how to turn it into a Power BI report for an
education committee: one page to read this year's result correctly, one to compare
municipalities.

## Tables (reports/bi/)

| File | Grain | Key columns |
|---|---|---|
| `dim_municipality.csv` | municipality | `municipality` (text, keep leading zero), `name`, `county`, `stockholm_county`, `cohort_median` |
| `dim_year.csv` | spring term | `year` |
| `fact_results.csv` | municipality × year | `merit`, `expected`, `resid`, `cohort_est`, `parents_post_secondary`, `foreign_background` |
| `fact_effects.csv` | municipality | `eb_mean`, `lo95`, `hi95`, `verdict`, `rank_point`, `rank_lo`, `rank_hi` |
| `v_change_vs_noise.csv` | municipality × year (from 2016) | `change`, `change_vs_national`, `noise_band_95`, `outside_band` |
| `v_municipality_card.csv` | municipality | latest year, three-year average residual, persistent effect, rank interval, latest change vs band |

Import `municipality` as **text** in Power Query, or Upplands Väsby (`0114`) becomes 114.

## Relationships

```
dim_municipality 1 ──< fact_results >── 1 dim_year
dim_municipality 1 ──< v_change_vs_noise >── 1 dim_year
dim_municipality 1 ── 1 fact_effects
dim_municipality 1 ── 1 v_municipality_card
```

Single direction, from dimensions to facts. `fact_effects` and `v_municipality_card` are
one row per municipality, so they can also be merged into `dim_municipality` in Power Query.

## Measures (DAX)

```dax
Merit value = AVERAGE ( fact_results[merit] )

Expected merit value = AVERAGE ( fact_results[expected] )

Difference from expected = [Merit value] - [Expected merit value]

-- Pupil-weighted, so large municipalities count more in county or national totals
Merit value (pupil-weighted) =
DIVIDE (
    SUMX ( fact_results, fact_results[merit] * fact_results[cohort_est] ),
    SUM ( fact_results[cohort_est] )
)

Three-year difference =
VAR LastYear = MAX ( dim_year[year] )
RETURN
    CALCULATE (
        [Difference from expected],
        dim_year[year] > LastYear - 3,
        dim_year[year] <= LastYear
    )

Change inside noise band =
IF (
    SELECTEDVALUE ( v_change_vs_noise[outside_band] ) = 1,
    "More than noise",
    "Within normal noise"
)

Municipalities above expected =
CALCULATE ( COUNTROWS ( fact_effects ), fact_effects[verdict] = "above" )

Municipalities below expected =
CALCULATE ( COUNTROWS ( fact_effects ), fact_effects[verdict] = "below" )
```

## Pages

**1. "Is this year's change real?"** (one municipality, selected with a slicer)
- Card row: merit value this year, change from last year, the 95 % noise band for the
  municipality's size, and the verdict from `Change inside noise band`.
- Line chart: merit value and expected value by year (2015–2025).
- Text box with the rule from the README: a change inside the band is normal noise.

**2. "How do we compare?"**
- Bar chart sorted by `eb_mean` with error bars from `lo95`/`hi95` (persistent difference
  from expected), the selected municipality highlighted.
- Table: name, cohort, three-year difference, rank interval (`rank_lo`–`rank_hi`), verdict.
- Map (filled map or shape map on municipality name) coloured by `verdict`.
- Slicers: county, size band, verdict.

Checks before publishing: the counts on page 2 should read 65 above, 82 below and 143 not
distinguishable (as in `reports/bi/v_verdict_counts.csv` and the README), and Stockholm
county 24 of 26 above.
