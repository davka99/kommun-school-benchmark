# Decisions and assumptions log

Each entry: what, why, alternatives, expected impact. Entries made **after** results were seen are marked *post-result* and say whether they are a diagnostic fix or a choice.

## D1 — Population: pupils by home municipality (hemkommun)
- **What:** the primary outcome is the merit value of grade-9 pupils registered in the municipality, whatever school provider they attend.
- **Why:** the municipality is responsible for all resident pupils; municipal-schools-only figures change when pupils move between providers, which mixes school choice with results.
- **Alternatives:** municipal schools only (robustness check in M7).
- **Impact:** in municipalities with many independent schools (e.g. Stockholm county) the two can differ.
- **Amendment (Run 1, after the first probe, before any outcome value was looked at):** the first probe's KPI list shows that Kolada's pupil-background KPIs (parents' education N15816, foreign background N15818, newly arrived in grade 9 N15819) are published by *school location* (lägeskommun), not by home municipality; only the newly-arrived share for grades 1–9 (N15901) is by home municipality. A model must have outcome and background measured on the same pupils. Rule, fixed now: **the primary population is the one where outcome and background refer to the same pupils.** M2 checks whether home-municipality background for grade 9 can be obtained from the original source (Skolverket); if yes, hemkommun stays primary; if not, lägeskommun (pupils in schools located in the municipality, N15504) becomes primary and hemkommun (N15507) is a robustness check using the closest available covariates. This is decided on data availability only, before any model or residual, and recorded in the tracking issue.

## D2 — Outcome: average merit value (17 subjects)
- **Why:** it is the headline measure in SKR's and Skolverket's comparisons and is continuous, so it carries more information than an eligibility share.
- **Alternative:** share eligible for a vocational upper-secondary programme (secondary outcome / robustness).
- **Known breaks:** no national tests in spring 2020–2021 (COVID), new syllabi from autumn 2022. Checked in M3; a year fixed effect absorbs national level shifts.

## D3 — A cohort is treated as a draw from the municipality's "process"
- **What:** the figures are a census of each cohort, not a sample, yet we model year-to-year variation as noise around a persistent municipality level.
- **Why:** the committee's question is about the municipality's lasting performance, not about the particular pupils who left in one year. This is the same super-population view used in value-added work.
- **Impact:** intervals describe how well the persistent level is pinned down, not sampling error of a survey.

## D4 — Covariates are frozen before any residual is computed
- The probe (M1) lists what is available. In M2 the covariate set is written here and committed before the model is fitted on the outcome. Variables that are themselves results of schooling (e.g. grades in earlier years) are excluded.

## D5 — Data access through GitHub Actions
- **What:** Kolada, SCB and package indexes are not reachable from the build sandbox, so downloads and statsmodels/geopandas work run in GitHub Actions (`pipeline_request.txt` triggers the workflow on the project branch).
- **Kolada API version:** v3 is tried first, v2 is the fallback; the probe records which answered.

## D6 — Municipality boundaries from SCB DeSO, dissolved
- **What:** SCB publishes DeSO (demographic statistical areas) as open geodata (CC0). DeSO codes start with the municipality code, so dissolving by `code[:4]` gives municipality polygons from an official source.
- **Alternative:** community GeoJSON (okfse/sweden-geojson) as a fallback if the SCB file cannot be found; recorded in the probe report if used.
- **Simplification:** 200 m tolerance in SWEREF 99 TM, for figures only — no analysis uses areas.
