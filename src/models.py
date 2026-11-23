"""M5-M6 models.

- Expected value: OLS with the frozen covariates (D8) + year fixed effects,
  standard errors clustered by municipality (statsmodels; runs in Actions).
- Persistent vs noise: random-intercept model (statsmodels MixedLM, REML) and an
  extension with size-dependent noise, sigma^2_it = c + d / n_it, fitted here by
  maximum likelihood on the fixed-part residuals (numpy/scipy, tested locally).
- Empirical-Bayes municipality effects, reliability and simulated rank intervals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dataset import COVARIATES


# ---------- expected value (statsmodels) ----------

def formula(outcome: str = "merit", covars=tuple(COVARIATES), extra: str = "") -> str:
    return f"{outcome} ~ {' + '.join(covars)} + C(year){extra}"


def model_frame(p: pd.DataFrame, outcome: str, covars) -> pd.DataFrame:
    return p.dropna(subset=[outcome, *covars, "cohort_est"]).reset_index(drop=True)


def fit_ols(d: pd.DataFrame, f: str):
    import statsmodels.formula.api as smf

    groups = d["municipality"].astype("category").cat.codes.to_numpy()
    return smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": groups})


def coef_table(m, names) -> dict:
    ci = m.conf_int()
    return {n: {"coef": round(float(m.params[n]), 3), "ci95": [round(float(ci.loc[n, 0]), 3),
                                                              round(float(ci.loc[n, 1]), 3)],
                "p": float(m.pvalues[n])} for n in names}


def reset_pvalue(m, d: pd.DataFrame, f: str) -> float:
    """RESET-style test: p-value of fitted^2 added to the model (clustered SE)."""
    d2 = d.assign(_fitted2=(m.fittedvalues - m.fittedvalues.mean()) ** 2)
    return float(fit_ols(d2, f + " + _fitted2").pvalues["_fitted2"])


def within_year_r2(d: pd.DataFrame, fitted: pd.Series, outcome: str) -> float:
    """Share of the between-municipality variance (within years) explained by the covariates."""
    y = d[outcome] - d.groupby("year")[outcome].transform("mean")
    f = fitted - fitted.groupby(d["year"]).transform("mean")
    return float(1 - ((y - f) ** 2).sum() / (y ** 2).sum())


# ---------- variance components ----------

def reliability(tau2: float, sigma2, k=1):
    """Reliability of a k-year average residual as a measure of the persistent effect."""
    return k * tau2 / (k * tau2 + np.asarray(sigma2, dtype=float))


def sigma2_of_n(n, c: float, dcoef: float):
    return c + dcoef / np.asarray(n, dtype=float)


def _group_arrays(r: np.ndarray, groups: np.ndarray, n: np.ndarray):
    order = np.argsort(groups, kind="stable")
    g, r, n = groups[order], r[order], n[order]
    cuts = np.flatnonzero(g[1:] != g[:-1]) + 1
    return np.split(g, cuts), np.split(r, cuts), np.split(n, cuts)


def marginal_loglik(r_list, n_list, tau2: float, c: float, dcoef: float) -> float:
    """Sum over municipalities of log N(r_i | 0, tau2*11' + diag(c + d/n_it)).

    Uses the closed form for a diagonal-plus-rank-one covariance.
    """
    ll = 0.0
    for r, n in zip(r_list, n_list):
        v = c + dcoef / n
        w = 1.0 / v
        s1, s2 = w.sum(), (w * r).sum()
        denom = 1.0 + tau2 * s1
        quad = (w * r * r).sum() - tau2 * s2 * s2 / denom
        logdet = np.log(v).sum() + np.log(denom)
        ll += -0.5 * (len(r) * np.log(2 * np.pi) + logdet + quad)
    return float(ll)


def fit_hetero(r: np.ndarray, groups: np.ndarray, n: np.ndarray, start=(30.0, 5.0, 5000.0)) -> dict:
    """ML estimates of tau2, c, d (all >= 0 via log-parametrisation)."""
    from scipy.optimize import minimize

    _, r_list, n_list = _group_arrays(np.asarray(r, float), np.asarray(groups), np.asarray(n, float))

    def nll(theta):
        tau2, c, dcoef = np.exp(theta)
        return -marginal_loglik(r_list, n_list, tau2, c, dcoef)

    res = minimize(nll, np.log(start), method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-6,
                                                                       "maxiter": 4000})
    tau2, c, dcoef = np.exp(res.x)
    return {"tau2": float(tau2), "c": float(c), "d": float(dcoef), "loglik": float(-res.fun),
            "converged": bool(res.success)}


def eb_effects(r, groups, n, tau2: float, c: float, dcoef: float) -> pd.DataFrame:
    """Posterior mean and SD of each municipality's persistent effect u_i.

    Prior u_i ~ N(0, tau2); r_it | u_i ~ N(u_i, c + d/n_it). With d = 0 this is the
    usual homoskedastic random-intercept BLUP.
    """
    g_list, r_list, n_list = _group_arrays(np.asarray(r, float), np.asarray(groups), np.asarray(n, float))
    rows = []
    for g, rr, nn in zip(g_list, r_list, n_list):
        w = 1.0 / (c + dcoef / nn)
        prec = 1.0 / tau2 + w.sum()
        mean = (w * rr).sum() / prec
        rows.append({"municipality": g[0], "years": len(rr), "raw_mean_resid": float(rr.mean()),
                     "eb_mean": float(mean), "eb_sd": float(np.sqrt(1.0 / prec)),
                     "data_weight": float(1 - (1.0 / tau2) / prec)})
    e = pd.DataFrame(rows)
    e["lo95"] = e["eb_mean"] - 1.959964 * e["eb_sd"]
    e["hi95"] = e["eb_mean"] + 1.959964 * e["eb_sd"]
    e["verdict"] = np.select([e["lo95"] > 0, e["hi95"] < 0], ["above", "below"], "not distinguishable")
    return e


def rank_intervals(e: pd.DataFrame, draws: int = 10000, seed: int = 0) -> pd.DataFrame:
    """Simulated 95 % rank intervals (rank 1 = furthest above expected).

    Draws are independent normals from each municipality's EB posterior; this ignores
    uncertainty in tau2 and the fixed effects, so intervals are, if anything, too narrow.
    """
    rng = np.random.default_rng(seed)
    m, s = e["eb_mean"].to_numpy(), e["eb_sd"].to_numpy()
    sims = rng.normal(m, s, size=(draws, len(m)))
    ranks = (-sims).argsort(axis=1).argsort(axis=1) + 1
    out = e[["municipality"]].copy()
    out["rank_point"] = (-m).argsort().argsort() + 1
    out["rank_lo"] = np.percentile(ranks, 2.5, axis=0).astype(int)
    out["rank_hi"] = np.percentile(ranks, 97.5, axis=0).astype(int)
    out["rank_median"] = np.median(ranks, axis=0)
    out["p_top_decile"] = (ranks <= round(0.1 * len(m))).mean(axis=0)
    out["p_bottom_decile"] = (ranks > len(m) - round(0.1 * len(m))).mean(axis=0)
    return out


def change_threshold(n, c: float, dcoef: float, z: float = 1.959964):
    """95 % range of a one-year change in a municipality's residual that is pure noise
    (independent years, the same cohort size both years)."""
    return z * np.sqrt(2 * sigma2_of_n(n, c, dcoef))


def lag1_autocorrelation(d: pd.DataFrame, col: str) -> float:
    s = d.sort_values(["municipality", "year"])
    prev = s.groupby("municipality")[col].shift()
    ok = prev.notna() & (s["year"] - s.groupby("municipality")["year"].shift() == 1)
    return float(np.corrcoef(s.loc[ok, col], prev[ok])[0, 1])
