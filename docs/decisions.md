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

## Probe findings that M2 must act on (Run 1, coverage only — no model, no residual)
- **Kolada API v3** answered (keys `count`, `values`, `next_url`, `previous_url`); v2 not needed.
- **Merit value** is available for all 290 municipalities in every year 2015–2025 for school location (N15504), municipal schools (N15505) and home municipality (N15507; 289 in 2019). Independent schools in the municipality (N15506) exist for only 117–133 municipalities.
- **Background KPIs** are by school location and cover grades 1–9: parents with post-secondary education (N15816, 290/290 every year), foreign background (N15818, 290/290). Newly arrived/unknown background *in grade 9* (N15819) has gaps (153 in 2015, ~230 from 2020, none in 2025). Newly arrived grades 1–9 by home municipality (N15901) covers 284–290.
- **No grade-9 cohort count** at municipality level in Kolada; pupils in grades 1–9 (N15807, N15829) are a size proxy (÷ 9).
- **Published model values:** SALSA KPIs (U15413–U15416) have no municipality-level values (school-unit data only); Kolada's own model (N15090/N15091) exists only for 2025 and only for eligibility.
- **Geodata:** SCB WFS layer `stat:DeSO_2025` (6,160 DeSO, SWEREF 99 TM) dissolves to exactly 290 municipalities (D6). The SCB web pages have no direct file links; the WFS is used and the community fallback is not needed.

## D7 — Primary population: pupils in schools located in the municipality (lägeskommun) — applies the D1 rule
- **Evidence (Run 2 `probe_scb`):** SCB's database has grade-9 merit value by parents' education only at national level (table `LE0201Utb/Tema42`); no municipality-level grade-9 background by home municipality exists in Kolada or SCB. Skolverket's own files are not reachable through an API.
- **Decision (pre-results):** outcome = **N15504** (merit value, 17 subjects, pupils in schools located in the municipality, both sexes), because the background KPIs are measured on that population.
- **Robustness:** home municipality (N15507) and municipal schools (N15505) with the same covariates, labelled as a population mismatch.
- **Business reading:** the result describes *the schools located in the municipality* (municipal and independent). That is what Öppna jämförelser's "lägeskommun" view and most local reporting use.

## D8 — Frozen covariates (pre-results; no outcome model had been fitted when this was written)
Primary model, municipality *i*, spring term *t*:

`merit_it = b0 + b1·parents_post_secondary_it + b2·foreign_background_it + year_t + u_i + e_it`

| Variable | KPI | Population | Why |
|---|---|---|---|
| parents_post_secondary | N15816 | grades 1–9, schools in the municipality | the strongest single predictor of grades in SALSA and in the research literature; complete 290/290 every year |
| foreign_background | N15818 | grades 1–9, schools in the municipality | captures language/migration background; complete 290/290 |
| year_t | — | — | absorbs national shifts (COVID 2020–21 without national tests, new syllabi 2022, grade inflation) |

- **Not included, and why:**
  - *Newly arrived in grade 9* (N15819): missing for 58–137 municipalities in 2015 and 2020–24 and absent in 2025. Instead a robustness check uses the outcome **excluding** newly arrived pupils (N15566).
  - *Share of boys*: not published at municipality level.
  - *Municipality size*: not a background characteristic; it is used to model noise (D10), not to adjust the level.
  - *Earlier grades, costs, teacher density*: these are outcomes or inputs of the school system, not pupil background; adjusting for them would remove part of what the committee is judged on.
- **Grade mismatch:** background refers to grades 1–9, the outcome to grade 9. At municipality level the two are highly correlated; the SALSA comparison (D9) checks this.
- **Functional form:** linear, as fixed here. Changes after diagnostics (e.g. a squared term) are logged as diagnostic fixes with before/after.

## D9 — Reconciliation against Skolverket's SALSA (school-unit data)
- Kolada publishes SALSA expected merit value (U15415) and deviation (U15416) for **school units** (4,564 units, 1,026–1,504 with values per year). Averaged over the schools located in each municipality they give an independent, grade-9-specific "expected value" (SALSA also uses share of boys and newly arrived).
- Used to (a) correlate our expected value with SALSA's, (b) correlate our residuals with the averaged SALSA deviation, and (c) as a robustness check with the averaged SALSA expected value as the only covariate.
- Caveat: no pupil counts per school are available, so the average is unweighted (each school counts once).

## D10 — Analysis plan (pre-registered)
- **Window:** spring terms 2015–2025; robustness without 2020–2021.
- **Expected value (M5):** OLS with the D8 covariates and year fixed effects, standard errors clustered by municipality. Diagnostics: residual vs fitted, by size, by county; influence (Cook's distance).
- **Persistent vs noise (M6):** linear mixed model (statsmodels MixedLM, REML), random intercept per municipality. Reported: τ (between-municipality SD of the persistent part), σ (year-to-year SD), ICC = τ²/(τ²+σ²), reliability of a 1-year and a k-year average = kτ²/(kτ²+σ²), with parametric-bootstrap intervals (seed fixed).
- **Size-dependent noise:** σ² is expected to fall with cohort size. Robustness: σ²_i = a + b / n_i, with n_i = pupils in grades 1–9 ÷ 9 (N15807; no grade-9 count exists).
- **"Consistently better/worse":** the 95 % interval of the empirical-Bayes municipality effect excludes 0. Multiple comparisons: the count of such municipalities is compared with what 290 null municipalities would give (expected 5 % false positives ≈ 14); reported as such.
- **Rank intervals:** 10,000 draws from the approximate posterior of the municipality effects (seed fixed); 95 % interval of each municipality's rank.
- **Decision rule:** the change in a municipality's residual from one year to the next that a committee should treat as noise = 95 % range of year-to-year residual differences, by size group; compared with the observed distribution of differences.
- **Rank stability (M4):** Spearman correlation of raw and residual ranks between consecutive years.
- **Spatial (M7):** Moran's I on empirical-Bayes effects, queen contiguity, 999 permutations; Gotland (no land neighbours) is linked to its nearest neighbour by centroid.
- **Robustness (M7):** home municipality; municipal schools; excluding newly arrived (N15566); without 2020–21; SALSA-average covariate; size-dependent noise.

## D11 — Rule for changing the functional form (written in Run 4, before the expected-value model was fitted)
- The primary model stays linear (D8) unless the diagnostics show clear curvature: a RESET test (fitted² added) with p < 0.01 **and** an increase in R² of at least 0.01 when a squared term for parents' education is added. If both hold, the squared term is added and logged here as a *diagnostic fix* with both versions reported; otherwise the linear model is kept and the RESET result is reported.
- Heteroskedasticity by size is expected (D10) and handled in M6, not by changing the expected-value model.

## D12 — *Post-result, diagnostic fix:* squared term for parents' education (D11 rule applied)
- RESET p = 6 × 10⁻⁸ and R² rose from 0.519 to 0.544 (+0.025) with the squared term, so the D11 rule added it. The square is centred and scaled, `((parents − 50)/10)²`: the same model, but MixedLM hit a singular matrix with the raw square.
- Effect: the curve is steeper at high parental education (Danderyd, Lidingö …). Both versions are in `reports/expected_value.json`.

## D13 — *Post-result, diagnostic fix:* size-dependent noise is used for the municipality effects
- Pre-registered (D10): homoskedastic mixed model primary, size-dependent noise as robustness.
- Diagnostics: Breusch–Pagan p ≈ 2 × 10⁻³⁵; residual SD 16.9 points in municipalities under 50 pupils vs 7.9–8.2 above 200; likelihood-ratio statistic 864 for σ²(n) = c + d/n vs constant σ². A constant σ² understates the noise for small municipalities and overstates it for large ones, so their intervals would be wrong in opposite directions.
- Change: effects, verdicts and rank intervals use the size-dependent model. The homoskedastic results are reported next to them (verdicts 70 above / 73 below vs 65 / 82; correlation of effects 0.994), so the change can be audited and does not drive the conclusion.

## D14 — *Post-result, diagnostic fix:* buffered contiguity for Moran's I
- The first robustness run built queen contiguity on the simplified (200 m) municipality layer and libpysal reported **69 disconnected components** — simplification opens slivers between neighbours, so many real neighbours were not linked. Weights are now "fuzzy" contiguity: polygons that touch after a 500 m buffer are neighbours; Gotland is linked to its nearest neighbour. The number of components is reported with each Moran's I. The first result (I = 0.31 for the persistent effects) is kept in this log for comparison; with the buffered weights (1 component, 5.5 neighbours on average) I = 0.32.

## D15 — SCB level gap explained (after publication)
The external check in `docs/data_quality.md` left a 7–9 point gap to SCB's national table
unexplained (denominator suspected, not verified). It is now explained: SCB's
LE0201Utb/Tema42 is the **16-subject** merit value, Kolada's N15504 the **17-subject**
value. Weighting SCB's girls and boys by the girls' share implied by Kolada reproduces
Skolverket's published 16-subject national averages for 2020–2022 exactly (222.9, 223.9,
221.2), and Kolada's total equals the published 17-subject averages (231.1, 232.1, 229.2,
227.6). Sources are in `data/reference/skolverket_published_merit.csv`. The denominator
hypothesis is withdrawn. No analysis result changes; the outcome stays the 17-subject
value, Skolverket's headline measure.

## D16 — SQL/BI layer (after publication)
The decision rules from the README are also written in SQL (`sql/02_views.sql`) on a star
schema loaded from the committed results, and exported to `reports/bi/` for Power BI
(`docs/powerbi.md`). SQLite is used so that it runs anywhere without a server; `sqrt()` is
registered from Python because not every SQLite build has math functions. The noise-band
view follows `src/descriptives.py` exactly (change demeaned by the year's mean change,
band from this year's cohort), and `tests/test_sql_layer.py` checks that the SQL gives the
same counts and shares as the Python results. The report itself (.pbix/.pbip) is not in
the repository: it needs Power BI Desktop.
