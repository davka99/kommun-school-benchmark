"""M4 descriptives: rank stability, churn, an implied cohort-noise model and funnel limits.

Everything here uses the raw outcome (no background adjustment yet).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dataset import weighted_national
from quality import year_to_year_changes

Z95, Z998 = 1.959964, 3.090232


def rank_stability(p: pd.DataFrame, col: str) -> pd.DataFrame:
    """Spearman correlation of municipality values between consecutive years."""
    w = p.pivot(index="municipality", columns="year", values=col)
    rows = []
    for a, b in zip(w.columns[:-1], w.columns[1:]):
        pair = w[[a, b]].dropna()
        rows.append({"year_from": int(a), "year_to": int(b), "n": int(len(pair)),
                     "spearman": round(float(pair[a].rank().corr(pair[b].rank())), 3)})
    return pd.DataFrame(rows)


def decile_churn(p: pd.DataFrame, col: str, share: float = 0.1) -> pd.DataFrame:
    """Of the top (bottom) `share` of municipalities in year t, the share still there in t+1."""
    w = p.pivot(index="municipality", columns="year", values=col)
    rows = []
    for a, b in zip(w.columns[:-1], w.columns[1:]):
        pair = w[[a, b]].dropna()
        k = int(round(share * len(pair)))
        top_a, top_b = set(pair[a].nlargest(k).index), set(pair[b].nlargest(k).index)
        bot_a, bot_b = set(pair[a].nsmallest(k).index), set(pair[b].nsmallest(k).index)
        rows.append({"year_from": int(a), "k": k, "top_stay": round(len(top_a & top_b) / k, 3),
                     "bottom_stay": round(len(bot_a & bot_b) / k, 3)})
    return pd.DataFrame(rows)


def demeaned_changes(p: pd.DataFrame, col: str = "merit") -> pd.DataFrame:
    """Year-to-year changes minus that year's mean change (removes national shifts)."""
    ch = year_to_year_changes(p, col)
    ch = ch.assign(change_dm=ch["change"] - ch.groupby("year")["change"].transform("mean"))
    return ch


def fit_noise(ch: pd.DataFrame) -> dict:
    """Fit E[change_dm^2] = a + b / n by least squares.

    If a cohort of n pupils is a draw with pupil-level SD s, the difference of two
    cohort means has variance 2 s^2 / n; `a` collects everything that does not shrink
    with size (real year-to-year shifts in the municipality). So s = sqrt(b / 2).
    """
    n = ch["cohort_est"].to_numpy()
    y = ch["change_dm"].to_numpy() ** 2
    X = np.column_stack([np.ones_like(n), 1.0 / n])
    (a, b), *_ = np.linalg.lstsq(X, y, rcond=None)
    return {"a": float(a), "b": float(b), "pupil_sd": float(np.sqrt(max(b, 0) / 2)),
            "size_free_sd": float(np.sqrt(max(a, 0) / 2))}


def fit_noise_bootstrap(ch: pd.DataFrame, reps: int = 1000, seed: int = 0) -> dict:
    """Point estimate + 95 % percentile interval, resampling municipalities (clusters)."""
    point = fit_noise(ch)
    rng = np.random.default_rng(seed)
    groups = {m: g for m, g in ch.groupby("municipality")}
    ids = np.array(sorted(groups))
    draws = []
    for _ in range(reps):
        pick = rng.choice(ids, size=len(ids), replace=True)
        draws.append(fit_noise(pd.concat([groups[m] for m in pick])))
    d = pd.DataFrame(draws)
    ci = {k: [round(float(d[k].quantile(0.025)), 2), round(float(d[k].quantile(0.975)), 2)] for k in d}
    return {"point": {k: round(v, 2) for k, v in point.items()}, "ci95": ci, "reps": reps, "seed": seed}


def change_sd(n, a: float, b: float):
    """SD of a year-demeaned one-year change for a municipality with cohort n."""
    return np.sqrt(a + b / np.asarray(n, dtype=float))


def funnel(p: pd.DataFrame, col: str, year: int, pupil_sd: float) -> pd.DataFrame:
    """Deviation from the pupil-weighted national mean vs cohort size, with noise limits."""
    nat = weighted_national(p, col)[year]
    f = p[p["year"] == year][["municipality", "name", "cohort_est", col]].dropna().copy()
    f["deviation"] = f[col] - nat
    se = pupil_sd / np.sqrt(f["cohort_est"])
    f["limit95"], f["limit998"] = Z95 * se, Z998 * se
    f["outside95"] = f["deviation"].abs() > f["limit95"]
    f["outside998"] = f["deviation"].abs() > f["limit998"]
    return f.sort_values("cohort_est").reset_index(drop=True)


def summarise(p: pd.DataFrame, year: int = 2025, seed: int = 0) -> dict:
    rs = rank_stability(p, "merit")
    churn = decile_churn(p, "merit")
    ch = demeaned_changes(p, "merit")
    noise = fit_noise_bootstrap(ch, seed=seed)
    fun = funnel(p, "merit", year, noise["point"]["pupil_sd"])
    a, b = noise["point"]["a"], noise["point"]["b"]
    bands = {str(n): round(float(Z95 * change_sd(n, a, b)), 1) for n in (30, 50, 100, 200, 500, 1000)}
    inside = (ch["change_dm"].abs() <= Z95 * change_sd(ch["cohort_est"], a, b)).mean()
    return {
        "rank_stability": rs.to_dict(orient="records"),
        "rank_stability_mean": round(float(rs["spearman"].mean()), 3),
        "rank_stability_range": [float(rs["spearman"].min()), float(rs["spearman"].max())],
        "decile_churn": churn.to_dict(orient="records"),
        "top_decile_stay_mean": round(float(churn["top_stay"].mean()), 3),
        "bottom_decile_stay_mean": round(float(churn["bottom_stay"].mean()), 3),
        "noise_model": noise,
        "change_95_band_by_cohort": bands,
        "share_changes_inside_band": round(float(inside), 3),
        "funnel_year": year,
        "funnel_outside95": int(fun["outside95"].sum()),
        "funnel_outside998": int(fun["outside998"].sum()),
        "funnel_n": int(len(fun)),
    }
