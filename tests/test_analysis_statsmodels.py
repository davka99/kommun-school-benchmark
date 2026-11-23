"""End-to-end checks of the statsmodels parts on a small synthetic panel (run in CI)."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")

import analysis  # noqa: E402


def synthetic_panel(n_mun=60, years=range(2018, 2024), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_mun):
        n = float(rng.choice([40, 100, 300, 900]))
        u = rng.normal(0, 6)
        base_p = rng.uniform(35, 80)
        fb = rng.uniform(5, 45)
        for y in years:
            pps = base_p + rng.normal(0, 1)
            rows.append({"municipality": f"{i:04d}", "name": f"M{i}", "county": "01" if i < 10 else "12",
                         "year": y, "cohort_est": n, "parents_post_secondary": pps, "foreign_background": fb,
                         "merit": 170 + 1.0 * pps + u + rng.normal(0, np.sqrt(4 + 8000 / n))})
    return pd.DataFrame(rows)


def test_expected_value_recovers_slope_and_keeps_linear_form():
    out, d, f = analysis.expected_value(synthetic_panel())
    assert out["coefficients_linear"]["parents_post_secondary"]["ci95"][0] < 1.0 < \
        out["coefficients_linear"]["parents_post_secondary"]["ci95"][1]
    assert out["d11_use_quadratic"] is False and "I(" not in f
    assert {"expected", "resid"} <= set(d.columns) and len(d) == 360


def test_persistence_runs_and_returns_consistent_outputs():
    p = synthetic_panel()
    _, d, f = analysis.expected_value(p)
    out, eff = analysis.persistence(d, f, seed=1, boot_reps=3, rank_draws=200)
    assert len(eff) == 60 and eff["rank_lo"].le(eff["rank_hi"]).all()
    assert 3 < out["size_dependent"]["tau"] < 10
    v = out["size_dependent"]["verdicts"]
    assert sum(v.values()) == 60
