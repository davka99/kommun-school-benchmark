# QA

## 1. Full rerun from the committed raw data
`python scripts/run_pipeline.py quality descriptives expected persistence robustness` was run from scratch in GitHub Actions (run 45169941218, Python 3.12, pinned requirements) on the commit that holds the final README (`6714e81`).

| Output | Result of the rerun |
|---|---|
| `reports/persistence.json`, `reports/robustness.json`, `reports/descriptives.json` | byte-identical |
| `reports/expected_value.json` | identical except p-values in the 13th–15th significant digit (floating-point noise in the linear algebra) |
| `reports/municipality_effects.csv`, `robustness_effects.csv` | identical except a handful of values in the 4th decimal (same cause); no verdict or rank changed |
| `docs/data_quality.md` | one row differed: two changes tie at −40.4 points and the unstable sort picked a different one. Fixed with a stable sort (municipality code, then year); a second rerun (run 45170543760) reproduced the report byte for byte |
| figures | regenerated; no visible change |

All 36 numbers quoted in the README are recomputed from `reports/` by `scripts/check_readme.py`, which runs as a test.

## 2. Do the numbers agree with each other?
- Text, tables and figures read from the same JSON files; figure titles are generated from them.
- The decision thresholds in the README are the observed 95th percentiles of year-to-year residual changes (`persistence.json → change_check_by_size`), not the slightly wider model values; this is stated in Limitations.
- Two estimates of pupil-level noise differ: 76 points from year-to-year *changes* (M4) and 99 from *levels* (M6). The level-based estimate also absorbs slow drift (residual autocorrelation 0.15) and the grade 1–9 vs grade 9 mismatch in the size proxy. Only the observed changes are used for the decision rule.

## 3. Does the result answer the brief?
| Brief: "done means" | Where |
|---|---|
| Expected value with diagnostics | `reports/expected_value.json`, D11–D12 |
| Persistent vs year-to-year split with intervals | `persistence.json` (ICC 0.41, CI 0.36–0.45; reliability by size) |
| Rank intervals; how many differ from average | `municipality_effects.csv`; 147 of 290 |
| Decision rule for committees | README *Recommendation* |
| Map, Stockholm county, spatial check | `figures/map_persistent_effects.png`, `rank_intervals_stockholm.png`, `stockholm_county.csv`, Moran's I in `robustness.json` |

What the brief said would *not* answer the question is avoided: ranks are never shown without intervals, and residuals are never called value added.

## 4. The three strongest objections
1. **"Above expected" is just unmeasured background, not better schools.**
   Agreed that it can't be separated here, and the README says so. Evidence for it: effects cluster in space (Moran's I 0.32) and 24 of 26 Stockholm-county municipalities are above expected. The analysis therefore makes no claim about school quality; its claims are about *noise* (how much of a ranking is stable), which doesn't depend on what the stable part consists of. Identifying school effects would need pupil-level data with prior attainment (e.g. grade 6 results) or a natural experiment.
2. **Municipality-level background (grades 1–9) is too crude; Skolverket's SALSA uses pupil-level data.**
   Tested directly: SALSA's grade-9 expected values correlate 0.82 with ours and the residuals 0.75. With SALSA as the only covariate, 156 municipalities differ persistently (147 in the primary), the effects correlate 0.82 with the primary, and Stockholm county is still 24 of 26 above. The noise conclusions (ICC, thresholds) change little.
3. **Cohort size is estimated and cohorts are not independent draws, so the noise thresholds are wrong.**
   The thresholds in the README are not model outputs but observed 95th percentiles of year-to-year changes by size band, so they don't depend on the noise model or the size estimate. The model-based version (wider by 9–35 %) is in `persistence.json` for comparison, and the residual autocorrelation (0.15) that explains the gap is reported.
