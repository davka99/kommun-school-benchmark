# PLAN — kommun-school-benchmark

**Title:** How much of the municipal school ranking is noise? Grade-9 results vs pupil background in Sweden's 290 municipalities

## Business question
Education committees and school directors see their municipality ranked on grade-9 results every year (SKR *Öppna jämförelser*, Skolverket SALSA, newspapers). **Which municipalities do consistently better or worse than their pupils' background predicts, and how much of a single year's rank is noise that should not trigger action?** Full brief: `docs/brief.md`.

## Data and how it is fetched
| Source | Content | Access |
|---|---|---|
| [Kolada](https://www.kolada.se) API (`api.kolada.se`, v3 with v2 fallback) | Grade-9 merit value, eligibility, pupil background, cohort size and published model values per municipality and year (from Skolverket/SCB) | Open REST, no key |
| [SCB open geodata – DeSO](https://www.scb.se/vara-tjanster/oppna-data/oppna-geodata/demografiska-statistikomraden-deso/) | Small-area polygons, dissolved to the 290 municipalities | Open download, CC0 |

The build sandbox cannot reach these hosts or PyPI. `scripts/run_pipeline.py <stage>` does all network work and is run by `.github/workflows/kommun-school-benchmark-pipeline.yml`, triggered by pushing a change to `pipeline_request.txt` (`workflow_dispatch` only works for workflows on the default branch). Outputs are committed back to the branch.

## Methods
- Data quality: coverage per KPI and year, suppressed values for small municipalities, breaks (COVID 2020–21, new syllabi 2022), reconciliation of the national figure against Skolverket's published value.
- Expected merit value: OLS of merit value on frozen background covariates + year fixed effects (HC3 / municipality-clustered SEs), diagnostics, comparison with published model values where Kolada has them.
- Persistent vs year-to-year variation: linear mixed model (municipality random intercept, year fixed effects; statsmodels MixedLM), ICC and reliability of a one-year vs multi-year average, empirical-Bayes (shrunken) municipality effects.
- Ranking uncertainty: simulated rank intervals; how many municipalities are distinguishable from average; funnel plot by cohort size; year-to-year rank correlation (Spearman).
- Decision rule: smallest one-year change that exceeds noise, by cohort size.
- Geodata: maps (geopandas), Moran's I on residuals (queen contiguity, Gotland handled explicitly), Stockholm-county panel.
- Robustness: municipal schools only, excluding 2020–21, eligibility as outcome, alternative covariate sets, weighting by cohort size.

## Milestones (one per build run)
- [ ] M1 Scaffold, Kolada client + parsers with tests, workflows, source probe (KPI candidates, coverage, municipality register, geodata)
- [ ] M2 Verify probe; freeze KPI list, covariates and analysis plan in `decisions.md`; full fetch 2015–2025
- [ ] M3 Data-quality report (`docs/data_quality.md`) + analysis dataset with tests
- [ ] M4 Descriptives: raw ranks, year-to-year rank stability, funnel plot, first map
- [ ] M5 Expected-value model with diagnostics; reconciliation against published model values
- [ ] M6 Mixed model: persistent effects, ICC/reliability, shrinkage, rank intervals, decision rule
- [ ] M7 Spatial check, Stockholm county view, robustness checks
- [ ] M8 Final README with real results, figures, README-number test, QA rerun, PR

Max 15 build runs.

## Definition of Done
- [ ] All data fetched by a script; raw/processed data and geodata in the repo or reproducible by one command; sources and licences stated
- [ ] KPI list, covariates and analysis plan committed before any residual or rank was computed
- [ ] `docs/data_quality.md` with coverage, suppression, breaks and a reconciliation to a published figure
- [ ] Expected-value model with diagnostics and an explicit "not value added" caveat
- [ ] Persistent-vs-noise split with intervals (ICC, reliability) and rank intervals
- [ ] Concrete decision rule for committees, with its uncertainty
- [ ] Map + Stockholm-county view + spatial autocorrelation check
- [ ] Robustness table (≥ 4 variants) saying which findings depend on choices
- [ ] README per portfolio standard; every number in it recomputed by a test
- [ ] Pinned requirements, fixed seed, tests pass locally and in GitHub Actions; standalone workflows in `projects/kommun-school-benchmark/.github/workflows/`
- [ ] `docs/qa.md`: full rerun from scratch and the three strongest objections answered
