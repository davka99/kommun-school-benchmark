"""Build the municipality x year analysis panel from the raw Kolada and SALSA files.

Column names map to KPI ids in VARIABLES; nothing is dropped silently — every
exclusion is counted by quality.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from municipalities import county_of, is_kommun

# Analysis name -> Kolada KPI (both sexes). See docs/decisions.md D7-D9.
VARIABLES = {
    "merit": "N15504",            # primary outcome: schools located in the municipality
    "merit_home": "N15507",       # robustness: home municipality
    "merit_municipal": "N15505",  # robustness: municipal schools
    "merit_excl_new": "N15566",   # robustness: excl. newly arrived / unknown background
    "elig_vocational": "N15424",  # secondary outcome (schools located in the municipality)
    "parents_post_secondary": "N15816",
    "foreign_background": "N15818",
    "pupils_1_9": "N15807",
}
OUTCOMES = ["merit", "merit_home", "merit_municipal", "merit_excl_new", "elig_vocational"]
COVARIATES = ["parents_post_secondary", "foreign_background"]


def kommun_rows(raw: pd.DataFrame, gender: str = "T") -> pd.DataFrame:
    """Keep the 290 municipalities and one sex; drop Riket ('0000'), regions and Kolada groups."""
    return raw[(raw["gender"] == gender) & raw["municipality"].map(is_kommun)].copy()


def wide_panel(raw: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    k = kommun_rows(raw)
    k = k[k["kpi"].isin(VARIABLES.values()) & k["period"].isin(years)]
    dup = k.duplicated(["kpi", "municipality", "period"]).sum()
    if dup:
        raise ValueError(f"{dup} duplicated kpi x municipality x year rows")
    w = k.pivot(index=["municipality", "period"], columns="kpi", values="value")
    inv = {v: n for n, v in VARIABLES.items()}
    w = w.rename(columns=inv).reset_index().rename(columns={"period": "year"})
    for col in VARIABLES:
        if col not in w:
            w[col] = np.nan
    return w[["municipality", "year", *VARIABLES]]


def salsa_by_municipality(ou: pd.DataFrame) -> pd.DataFrame:
    """Unweighted mean of school-unit SALSA expected value (U15415) and deviation (U15416)."""
    o = ou[(ou["gender"] == "T") & ou["kpi"].isin(["U15415", "U15416"]) & ou["value"].notna()]
    g = o.pivot_table(index=["municipality", "period", "ou"], columns="kpi", values="value").reset_index()
    agg = g.groupby(["municipality", "period"]).agg(
        salsa_expected=("U15415", "mean"),
        salsa_deviation=("U15416", "mean"),
        salsa_units=("ou", "nunique"),
    ).reset_index().rename(columns={"period": "year"})
    return agg


def build_panel(raw: pd.DataFrame, ou: pd.DataFrame | None, names: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    p = wide_panel(raw, years)
    expected = len(names[names["id"].map(is_kommun)]) * len(years)
    if len(p) != expected:
        raise ValueError(f"panel has {len(p)} rows, expected {expected} (290 x years)")
    p["cohort_est"] = p["pupils_1_9"] / 9.0
    p["county"] = p["municipality"].map(county_of)
    p["stockholm_county"] = p["county"] == "01"
    nm = names.set_index("id")["title"]
    p.insert(1, "name", p["municipality"].map(nm))
    if ou is not None and len(ou):
        p = p.merge(salsa_by_municipality(ou), on=["municipality", "year"], how="left")
        p["salsa_units"] = p["salsa_units"].fillna(0).astype(int)
    return p.sort_values(["municipality", "year"]).reset_index(drop=True)


def weighted_national(p: pd.DataFrame, col: str, weight: str = "pupils_1_9") -> pd.Series:
    """Pupil-weighted mean of a municipality column per year (weights: grades 1-9 pupils)."""
    def f(g):
        g = g[g[col].notna() & g[weight].notna()]
        return float(np.average(g[col], weights=g[weight])) if len(g) else np.nan
    return p.groupby("year").apply(f, include_groups=False)
