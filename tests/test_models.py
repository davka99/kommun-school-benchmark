import numpy as np
import pandas as pd
import pytest
from scipy.stats import multivariate_normal

import models


def simulate(n_mun=300, years=11, tau=6.0, c=4.0, d=6000.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_mun):
        n = float(rng.choice([30, 60, 120, 250, 600, 2000]))
        u = rng.normal(0, tau)
        for t in range(years):
            rows.append({"municipality": f"{i:04d}", "year": 2015 + t, "cohort_est": n,
                         "r": u + rng.normal(0, np.sqrt(c + d / n)), "u": u})
    return pd.DataFrame(rows)


def test_marginal_loglik_matches_dense_multivariate_normal():
    r = np.array([1.0, -2.0, 0.5])
    n = np.array([50.0, 80.0, 200.0])
    tau2, c, d = 9.0, 3.0, 4000.0
    cov = tau2 * np.ones((3, 3)) + np.diag(c + d / n)
    expected = multivariate_normal(mean=np.zeros(3), cov=cov).logpdf(r)
    assert models.marginal_loglik([r], [n], tau2, c, d) == pytest.approx(expected, rel=1e-10)


def test_fit_hetero_recovers_simulated_parameters():
    s = simulate()
    fit = models.fit_hetero(s["r"].to_numpy(), s["municipality"].to_numpy(), s["cohort_est"].to_numpy())
    assert fit["converged"]
    assert np.sqrt(fit["tau2"]) == pytest.approx(6.0, rel=0.15)
    assert np.sqrt(fit["d"] / 2) == pytest.approx(np.sqrt(6000 / 2), rel=0.15)


def test_eb_homoskedastic_equals_textbook_blup():
    s = pd.DataFrame({"municipality": ["A"] * 4 + ["B"] * 2, "r": [2.0, 4.0, 3.0, 3.0, -1.0, -3.0],
                      "cohort_est": [100.0] * 6})
    tau2, sigma2 = 4.0, 8.0
    e = models.eb_effects(s["r"], s["municipality"], s["cohort_est"], tau2, sigma2, 0.0).set_index("municipality")
    lam_a = tau2 / (tau2 + sigma2 / 4)
    assert e.loc["A", "eb_mean"] == pytest.approx(lam_a * 3.0)
    assert e.loc["A", "eb_sd"] == pytest.approx(np.sqrt(1 / (1 / tau2 + 4 / sigma2)))
    assert e.loc["B", "eb_mean"] == pytest.approx(tau2 / (tau2 + sigma2 / 2) * -2.0)
    assert e.loc["A", "data_weight"] == pytest.approx(lam_a)


def test_eb_verdicts_and_coverage_on_simulation():
    s = simulate(seed=3)
    e = models.eb_effects(s["r"], s["municipality"], s["cohort_est"], 36.0, 4.0, 6000.0)
    truth = s.groupby("municipality")["u"].first().reindex(e["municipality"]).to_numpy()
    covered = ((e["lo95"] <= truth) & (truth <= e["hi95"])).mean()
    assert 0.9 < covered < 0.99
    assert set(e["verdict"]) <= {"above", "below", "not distinguishable"}


def test_rank_intervals_order_and_bounds():
    e = pd.DataFrame({"municipality": list("ABCD"), "eb_mean": [10.0, 0.0, -10.0, 0.1],
                      "eb_sd": [0.1, 3.0, 0.1, 3.0]})
    r = models.rank_intervals(e, draws=4000, seed=1).set_index("municipality")
    assert r.loc["A", "rank_lo"] == r.loc["A", "rank_hi"] == 1
    assert r.loc["C", "rank_lo"] == r.loc["C", "rank_hi"] == 4
    assert r.loc["B", "rank_lo"] == 2 and r.loc["B", "rank_hi"] == 3
    assert list(r["rank_point"]) == [1, 3, 4, 2]


def test_reliability_and_threshold():
    assert models.reliability(25.0, 75.0) == pytest.approx(0.25)
    assert models.reliability(25.0, 75.0, k=3) == pytest.approx(0.5)
    assert models.change_threshold(100, 0.0, 5000.0) == pytest.approx(1.959964 * np.sqrt(100))


def test_lag1_autocorrelation_detects_persistence():
    rng = np.random.default_rng(4)
    rows = []
    for i in range(200):
        x = 0.0
        for t in range(10):
            x = 0.8 * x + rng.normal()
            rows.append({"municipality": i, "year": 2015 + t, "e": x})
    assert models.lag1_autocorrelation(pd.DataFrame(rows), "e") > 0.6
