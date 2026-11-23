import numpy as np
import pandas as pd
import pytest

import descriptives as d


def panel_from(values: dict, cohort=100.0):
    rows = []
    for m, series in values.items():
        for y, v in series.items():
            rows.append({"municipality": m, "name": m, "year": y, "merit": v, "cohort_est": cohort,
                         "pupils_1_9": cohort * 9})
    return pd.DataFrame(rows)


def test_rank_stability_perfect_and_reversed():
    p = panel_from({"A": {2024: 1, 2025: 1}, "B": {2024: 2, 2025: 2}, "C": {2024: 3, 2025: 3}})
    assert d.rank_stability(p, "merit")["spearman"].iloc[0] == 1.0
    p = panel_from({"A": {2024: 1, 2025: 3}, "B": {2024: 2, 2025: 2}, "C": {2024: 3, 2025: 1}})
    assert d.rank_stability(p, "merit")["spearman"].iloc[0] == -1.0


def test_decile_churn_counts_stayers():
    vals = {f"M{i:02d}": {2024: i, 2025: i} for i in range(20)}
    vals["M19"][2025] = -1  # the top one drops to the bottom
    out = d.decile_churn(panel_from(vals), "merit").iloc[0]
    assert out["k"] == 2 and out["top_stay"] == 0.5 and out["bottom_stay"] == 0.5


def test_fit_noise_recovers_simulated_pupil_sd():
    rng = np.random.default_rng(1)
    rows = []
    s, drift = 70.0, 3.0
    for m in range(400):
        n = float(rng.choice([30, 60, 120, 300, 900]))
        for y in range(2015, 2026):
            rows.append({"municipality": f"{m:04d}", "name": "x", "year": y, "cohort_est": n,
                         "merit": 220 + rng.normal(0, s / np.sqrt(n))})
    ch = d.demeaned_changes(pd.DataFrame(rows))
    fit = d.fit_noise(ch)
    assert fit["pupil_sd"] == pytest.approx(s, rel=0.08)
    assert fit["size_free_sd"] < drift  # no size-free component was simulated


def test_bootstrap_is_reproducible_with_seed():
    rng = np.random.default_rng(2)
    rows = [{"municipality": f"{m}", "name": "x", "year": y, "cohort_est": 100.0,
             "merit": 220 + rng.normal(0, 7)} for m in range(30) for y in range(2020, 2025)]
    ch = d.demeaned_changes(pd.DataFrame(rows))
    a = d.fit_noise_bootstrap(ch, reps=50, seed=3)
    b = d.fit_noise_bootstrap(ch, reps=50, seed=3)
    assert a == b and a["ci95"]["pupil_sd"][0] < a["point"]["pupil_sd"] < a["ci95"]["pupil_sd"][1]


def test_funnel_limits_shrink_with_size_and_flag_outliers():
    p = pd.DataFrame({"municipality": ["A", "B", "C"], "name": ["A", "B", "C"], "year": [2025] * 3,
                      "merit": [200.0, 230.0, 260.0], "cohort_est": [25.0, 2500.0, 100.0],
                      "pupils_1_9": [225.0, 22500.0, 900.0]})
    f = d.funnel(p, "merit", 2025, pupil_sd=70.0).set_index("municipality")
    assert f.loc["A", "limit95"] > f.loc["C", "limit95"] > f.loc["B", "limit95"]
    assert f.loc["A", "limit95"] == pytest.approx(1.959964 * 70 / 5)
    assert bool(f.loc["C", "outside95"]) and not bool(f.loc["B", "outside95"])
