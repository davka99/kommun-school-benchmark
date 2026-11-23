"""M5 (expected value) and M6 (persistent effect vs noise). Needs statsmodels."""

from __future__ import annotations

import numpy as np
import pandas as pd

import models
from dataset import COVARIATES
from quality import size_bands

SIZES = (30, 50, 100, 200, 500, 1000)


def _r(x, k=3):
    return round(float(x), k)


def expected_value(p: pd.DataFrame, outcome: str = "merit", covars=tuple(COVARIATES)) -> tuple[dict, pd.DataFrame, str]:
    import statsmodels.formula.api as smf
    from statsmodels.stats.diagnostic import het_breuschpagan

    d = models.model_frame(p, outcome, covars)
    f_lin = models.formula(outcome, covars)
    m = models.fit_ols(d, f_lin)
    reset_p = models.reset_pvalue(m, d, f_lin)
    f_quad = f_lin + " + I(parents_post_secondary ** 2)"
    mq = models.fit_ols(d, f_quad)
    gain = mq.rsquared - m.rsquared
    use_quad = bool(reset_p < 0.01 and gain >= 0.01)  # D11 rule
    chosen_f, chosen = (f_quad, mq) if use_quad else (f_lin, m)

    d = d.assign(expected=chosen.fittedvalues, resid=chosen.resid)
    plain = smf.ols(chosen_f, d).fit()
    bp = het_breuschpagan(plain.resid, plain.model.exog)
    cooks = plain.get_influence().cooks_distance[0]
    top_cook = d.assign(cooks=cooks).nlargest(5, "cooks")[["name", "year", "cohort_est", outcome, "expected",
                                                            "resid", "cooks"]]
    sd_band = d.assign(band=size_bands(d["cohort_est"])).groupby("band", observed=True)["resid"].std()
    county = d.groupby("county")["resid"].mean().sort_values()

    out = {
        "outcome": outcome,
        "n_rows": int(len(d)),
        "n_municipalities": int(d["municipality"].nunique()),
        "formula_linear": f_lin,
        "coefficients_linear": models.coef_table(m, list(covars)),
        "r2_linear": _r(m.rsquared), "adj_r2_linear": _r(m.rsquared_adj),
        "within_year_r2_linear": _r(models.within_year_r2(d, m.fittedvalues, outcome)),
        "reset_p_linear": reset_p,
        "r2_gain_quadratic": _r(gain, 4),
        "d11_use_quadratic": use_quad,
        "formula_chosen": chosen_f,
        "coefficients_chosen": models.coef_table(chosen, [n for n in chosen.params.index if not n.startswith(("C(", "Intercept"))]),
        "r2_chosen": _r(chosen.rsquared),
        "within_year_r2_chosen": _r(models.within_year_r2(d, chosen.fittedvalues, outcome)),
        "resid_sd": _r(d["resid"].std(), 2),
        "breusch_pagan_p": float(bp[1]),
        "resid_sd_by_size": {str(k): _r(v, 2) for k, v in sd_band.items()},
        "corr_abs_resid_size": _r(d["resid"].abs().rank().corr(d["cohort_est"].rank())),
        "top_cooks_distance": top_cook.round(3).to_dict(orient="records"),
        "county_mean_resid_lowest": {k: _r(v, 2) for k, v in county.head(3).items()},
        "county_mean_resid_highest": {k: _r(v, 2) for k, v in county.tail(3).items()},
    }
    if "salsa_expected" in d:
        s = d[d["salsa_units"] > 0]
        ms = models.fit_ols(s, f"{outcome} ~ salsa_expected + C(year)")
        mo = models.fit_ols(s, chosen_f)
        out["salsa"] = {
            "rows": int(len(s)),
            "corr_expected": _r(s["expected"].corr(s["salsa_expected"])),
            "corr_resid_vs_salsa_deviation": _r(s["resid"].corr(s["salsa_deviation"])),
            "within_year_r2_salsa_only": _r(models.within_year_r2(s, ms.fittedvalues, outcome)),
            "within_year_r2_ours_same_rows": _r(models.within_year_r2(s, mo.fittedvalues, outcome)),
        }
    return out, d, chosen_f


def _fixed_residuals(mixed) -> np.ndarray:
    fe = mixed.fe_params.to_numpy()
    X = mixed.model.exog[:, : len(fe)]
    return mixed.model.endog - X @ fe


def fit_mixed(d: pd.DataFrame, f: str):
    import statsmodels.formula.api as smf

    return smf.mixedlm(f, d, groups=d["municipality"]).fit(reml=True, method="lbfgs")


def bootstrap_components(d: pd.DataFrame, f: str, mixed, reps: int, seed: int) -> dict:
    """Parametric bootstrap of tau, sigma and ICC under the fitted homoskedastic model."""
    rng = np.random.default_rng(seed)
    fe = mixed.fe_params.to_numpy()
    X = mixed.model.exog[:, : len(fe)]
    tau2, sigma2 = float(mixed.cov_re.iloc[0, 0]), float(mixed.scale)
    codes = d["municipality"].astype("category").cat.codes.to_numpy()
    outcome = f.split("~")[0].strip()
    res = []
    for _ in range(reps):
        u = rng.normal(0, np.sqrt(tau2), codes.max() + 1)
        y = X @ fe + u[codes] + rng.normal(0, np.sqrt(sigma2), len(codes))
        m = fit_mixed(d.assign(**{outcome: y}), f)
        t2, s2 = float(m.cov_re.iloc[0, 0]), float(m.scale)
        res.append({"tau": np.sqrt(t2), "sigma": np.sqrt(s2), "icc": t2 / (t2 + s2)})
    b = pd.DataFrame(res)
    return {k: [_r(b[k].quantile(0.025)), _r(b[k].quantile(0.975))] for k in b} | {"reps": reps, "seed": seed}


def persistence(d: pd.DataFrame, f: str, seed: int, boot_reps: int = 200, rank_draws: int = 10000) -> tuple[dict, pd.DataFrame]:
    mixed = fit_mixed(d, f)
    tau2, sigma2 = float(mixed.cov_re.iloc[0, 0]), float(mixed.scale)
    r = _fixed_residuals(mixed)
    groups, n = d["municipality"].to_numpy(), d["cohort_est"].to_numpy()

    het = models.fit_hetero(r, groups, n, start=(tau2, sigma2 / 2, sigma2 * 100))
    ll_homo = models.marginal_loglik(*models._group_arrays(r, groups, n)[1:], tau2, sigma2, 0.0)
    lr = 2 * (het["loglik"] - ll_homo)

    e_hom = models.eb_effects(r, groups, n, tau2, sigma2, 0.0)
    e_het = models.eb_effects(r, groups, n, het["tau2"], het["c"], het["d"])
    ranks = models.rank_intervals(e_het, draws=rank_draws, seed=seed)
    eff = e_het.merge(ranks, on="municipality")
    eff = eff.merge(e_hom[["municipality", "eb_mean", "verdict"]].rename(
        columns={"eb_mean": "eb_mean_homo", "verdict": "verdict_homo"}), on="municipality")
    info = d.groupby("municipality").agg(name=("name", "first"), county=("county", "first"),
                                         cohort_median=("cohort_est", "median"))
    eff = eff.merge(info, left_on="municipality", right_index=True)

    # single latest year vs persistent effect
    last = d["year"].max()
    dl = d.assign(r=r)
    one = dl[dl["year"] == last].set_index("municipality")["r"]
    eff["resid_last_year"] = eff["municipality"].map(one)
    k = round(0.1 * len(eff))
    top_one = set(eff.nlargest(k, "resid_last_year")["municipality"])
    top_eb = set(eff.nlargest(k, "eb_mean")["municipality"])
    bot_one = set(eff.nsmallest(k, "resid_last_year")["municipality"])
    bot_eb = set(eff.nsmallest(k, "eb_mean")["municipality"])

    # year-to-year change in residuals: model threshold vs observed, by size band
    dl = dl.merge(e_het[["municipality", "eb_mean"]], on="municipality")
    dl["within"] = dl["r"] - dl["eb_mean"]
    s = dl.sort_values(["municipality", "year"])
    s["dr"] = s.groupby("municipality")["r"].diff()
    s = s[s["dr"].notna()]
    s["thr"] = models.change_threshold(s["cohort_est"], het["c"], het["d"])
    s["dr_dm"] = s["dr"] - s.groupby("year")["dr"].transform("mean")
    band = s.assign(band=size_bands(s["cohort_est"])).groupby("band", observed=True)
    check = pd.DataFrame({"n": band.size(), "observed_p95_abs_change": band["dr_dm"].apply(lambda v: v.abs().quantile(.95)),
                          "model_threshold_mean": band["thr"].mean(),
                          "share_inside_model_threshold": band.apply(lambda g: (g["dr_dm"].abs() <= g["thr"]).mean(),
                                                                     include_groups=False)}).round(3)

    sizes = np.array(SIZES, float)
    sig_n = models.sigma2_of_n(sizes, het["c"], het["d"])
    counts = eff["verdict"].value_counts().to_dict()
    counts_h = eff["verdict_homo"].value_counts().to_dict()
    width = eff["rank_hi"] - eff["rank_lo"]
    out = {
        "formula": f,
        "homoskedastic": {"tau": _r(np.sqrt(tau2), 2), "sigma": _r(np.sqrt(sigma2), 2),
                          "icc": _r(tau2 / (tau2 + sigma2)),
                          "reliability_1y": _r(models.reliability(tau2, sigma2, 1)),
                          "reliability_3y": _r(models.reliability(tau2, sigma2, 3)),
                          "bootstrap_ci95": bootstrap_components(d, f, mixed, boot_reps, seed),
                          "verdicts": {k2: int(v) for k2, v in counts_h.items()}},
        "size_dependent": {"tau": _r(np.sqrt(het["tau2"]), 2), "c": _r(het["c"], 2), "d": _r(het["d"], 1),
                           "implied_pupil_sd": _r(np.sqrt(het["d"]), 1),
                           "size_free_noise_sd": _r(np.sqrt(het["c"]), 2),
                           "converged": het["converged"], "lr_vs_homoskedastic": _r(lr, 1),
                           "noise_sd_by_cohort": {str(int(z)): _r(np.sqrt(v), 2) for z, v in zip(sizes, sig_n)},
                           "reliability_1y_by_cohort": {str(int(z)): _r(models.reliability(het["tau2"], v, 1))
                                                         for z, v in zip(sizes, sig_n)},
                           "reliability_3y_by_cohort": {str(int(z)): _r(models.reliability(het["tau2"], v, 3))
                                                         for z, v in zip(sizes, sig_n)},
                           "change_threshold_by_cohort": {str(int(z)): _r(models.change_threshold(z, het["c"], het["d"]), 1)
                                                          for z in sizes},
                           "verdicts": {k2: int(v) for k2, v in counts.items()}},
        "expected_false_positives_if_no_differences": _r(0.05 * len(eff), 1),
        "rank_interval_width_median": int(width.median()),
        "rank_interval_width_quartiles": [int(width.quantile(.25)), int(width.quantile(.75))],
        "n_rank_interval_within_top_decile": int((eff["rank_hi"] <= k).sum()),
        "n_rank_interval_within_bottom_decile": int((eff["rank_lo"] > len(eff) - k).sum()),
        "n_with_p_top_decile_over_90": int((eff["p_top_decile"] > 0.9).sum()),
        "last_year": int(last),
        "spearman_last_year_resid_vs_eb": _r(eff["resid_last_year"].rank().corr(eff["eb_mean"].rank())),
        "top_decile_last_year_also_eb_top_decile": f"{len(top_one & top_eb)}/{k}",
        "bottom_decile_last_year_also_eb_bottom_decile": f"{len(bot_one & bot_eb)}/{k}",
        "lag1_autocorr_within_residual": _r(models.lag1_autocorrelation(dl, "within")),
        "change_check_by_size": check.reset_index().astype({"band": str}).to_dict(orient="records"),
        "corr_eb_homo_vs_size_dependent": _r(eff["eb_mean"].corr(eff["eb_mean_homo"])),
    }
    return out, eff.sort_values("eb_mean", ascending=False).reset_index(drop=True)
