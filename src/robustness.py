"""M7: robustness variants (D10) and the spatial check. Needs statsmodels; spatial needs libpysal/esda."""

from __future__ import annotations

import numpy as np
import pandas as pd

import analysis
import models

COVS = ["parents_post_secondary", "foreign_background"]


def effects_for(d: pd.DataFrame, f: str, size_dependent: bool = True) -> tuple[pd.DataFrame, dict]:
    """Municipality effects for one specification (no bootstrap)."""
    mixed = analysis.fit_mixed(d, f)
    tau2, sigma2 = float(mixed.cov_re.iloc[0, 0]), float(mixed.scale)
    r = analysis._fixed_residuals(mixed)
    g, n = d["municipality"].to_numpy(), d["cohort_est"].to_numpy()
    if size_dependent:
        h = models.fit_hetero(r, g, n, start=(max(tau2, 1.0), sigma2 / 2, sigma2 * 100))
        e = models.eb_effects(r, g, n, h["tau2"], h["c"], h["d"])
        stats = {"tau": np.sqrt(h["tau2"]), "threshold_100": float(models.change_threshold(100, h["c"], h["d"]))}
    else:
        e = models.eb_effects(r, g, n, tau2, sigma2, 0.0)
        stats = {"tau": np.sqrt(tau2), "threshold_100": float(models.change_threshold(100, sigma2, 0.0))}
    stats["icc_homoskedastic"] = tau2 / (tau2 + sigma2)
    return e, stats


def variants(p: pd.DataFrame, primary_f: str) -> dict[str, tuple[pd.DataFrame, str, bool]]:
    """name -> (model frame, formula, size_dependent). All pre-registered in D10 except where noted."""
    rhs = primary_f.split("~", 1)[1]
    lin_rhs = " parents_post_secondary + foreign_background + C(year)"
    out = {}
    base = models.model_frame(p, "merit", COVS)
    out["primary"] = (base, primary_f, True)
    out["homoskedastic noise"] = (base, primary_f, False)
    out["linear background (no square)"] = (base, "merit ~" + lin_rhs, True)
    for col, label in (("merit_home", "home municipality"), ("merit_municipal", "municipal schools only"),
                       ("merit_excl_new", "excl. newly arrived pupils")):
        out[label] = (models.model_frame(p, col, COVS), f"{col} ~" + rhs, True)
    out["without 2020–2021"] = (base[~base["year"].isin([2020, 2021])].reset_index(drop=True), primary_f, True)
    s = p[(p["salsa_units"] > 0)].dropna(subset=["merit", "salsa_expected", "cohort_est"]).reset_index(drop=True)
    out["SALSA expected value as covariate"] = (s, "merit ~ salsa_expected + C(year)", True)
    return out


def run(p: pd.DataFrame, primary_f: str, stockholm: str = "01") -> tuple[dict, pd.DataFrame]:
    rows, wide = [], None
    for name, (d, f, het) in variants(p, primary_f).items():
        e, st = effects_for(d, f, het)
        e = e[["municipality", "eb_mean", "verdict"]].rename(columns={"eb_mean": name, "verdict": f"verdict|{name}"})
        wide = e if wide is None else wide.merge(e, on="municipality", how="outer")
        rows.append({"variant": name, "rows": int(len(d)), "municipalities": int(d["municipality"].nunique()),
                     "tau": round(st["tau"], 2), "icc_homoskedastic": round(st["icc_homoskedastic"], 3),
                     "threshold_change_100_pupils": round(st["threshold_100"], 1)})
    county = wide["municipality"].str[:2]
    prim_above = set(wide.loc[wide["verdict|primary"] == "above", "municipality"])
    prim_below = set(wide.loc[wide["verdict|primary"] == "below", "municipality"])
    for r in rows:
        v = r["variant"]
        verdict = wide[f"verdict|{v}"]
        r["above"] = int((verdict == "above").sum())
        r["below"] = int((verdict == "below").sum())
        r["spearman_with_primary"] = round(float(wide[v].rank().corr(wide["primary"].rank())), 3)
        r["primary_above_still_above"] = f"{len(prim_above & set(wide.loc[verdict == 'above', 'municipality']))}/{len(prim_above)}"
        r["primary_below_still_below"] = f"{len(prim_below & set(wide.loc[verdict == 'below', 'municipality']))}/{len(prim_below)}"
        sc = verdict[county == stockholm]
        r["stockholm_county_above"] = f"{int((sc == 'above').sum())}/{int(sc.notna().sum())}"
        r["stockholm_county_mean_effect"] = round(float(wide.loc[county == stockholm, v].mean()), 2)
    return {"variants": rows}, wide


def spatial_weights(gdf, buffer_m: float = 500.0):
    """Contiguity with a small buffer, row-standardised.

    The municipality layer is simplified (200 m) for drawing, which opens slivers
    between neighbours: plain queen contiguity split Sweden into 69 disconnected
    components (Run 7). Polygons that touch after a 500 m buffer are neighbours.
    Islands (Gotland) are linked to their nearest neighbour by centroid.
    """
    from libpysal import weights
    from libpysal.weights.util import attach_islands

    g = gdf.reset_index(drop=True)
    w = weights.fuzzy_contiguity(g, buffering=True, buffer=buffer_m, silence_warnings=True)
    islands = list(w.islands)
    if islands:
        knn = weights.KNN.from_dataframe(g, k=1, use_index=False)
        w = attach_islands(w, knn)
    w.transform = "r"
    return w, islands


def morans_i(gdf, value_col: str, permutations: int = 999, seed: int = 0) -> dict:
    """Moran's I on `value_col` with buffered contiguity weights."""
    import esda

    g = gdf.reset_index(drop=True)
    w, islands = spatial_weights(g)
    np.random.seed(seed)
    mi = esda.Moran(g[value_col].to_numpy(), w, permutations=permutations)
    return {"I": round(float(mi.I), 3), "expected_I": round(float(mi.EI), 4), "p_permutation": float(mi.p_sim),
            "permutations": permutations, "islands_linked": [g.loc[i, "kommun"] for i in islands],
            "mean_neighbours": round(float(w.mean_neighbors), 2), "components": int(w.n_components),
            "n": int(len(g))}
