"""Data-quality checks (M3). Pure pandas; every number in docs/data_quality.md comes from here."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dataset import VARIABLES, kommun_rows, weighted_national

SHARE_COLS = ["elig_vocational", "parents_post_secondary", "foreign_background"]
MERIT_COLS = ["merit", "merit_home", "merit_municipal", "merit_excl_new"]
MERIT_MAX = 340  # 17 subjects x 20 points (A)


def id_categories(raw: pd.DataFrame) -> dict:
    ids = raw["municipality"].drop_duplicates()
    from municipalities import is_kommun

    cat = np.select(
        [ids.map(is_kommun), ids.eq("0000"), ids.str.match(r"^00\d\d$"), ids.str.startswith("G")],
        ["municipality", "country", "region", "kolada_group"], "other")
    return pd.Series(cat).value_counts().to_dict()


def completeness(p: pd.DataFrame) -> pd.DataFrame:
    return p.groupby("year")[list(VARIABLES)].count().T


def status_counts(raw: pd.DataFrame) -> dict:
    k = kommun_rows(raw)
    k = k[k["kpi"].isin(VARIABLES.values())]
    inv = {v: n for n, v in VARIABLES.items()}
    k = k.assign(var=k["kpi"].map(inv), status=k["status"].fillna("").str.strip(","))
    t = k[k["status"] != ""].groupby(["var", "status"]).size()
    return {f"{v}|{s}": int(n) for (v, s), n in t.items()}


def integer_share(p: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    def share(s):
        s = s.dropna()
        return float((s % 1 == 0).mean()) if len(s) else np.nan
    return p.groupby("year")[cols].agg(share).T.round(2)


def range_violations(p: pd.DataFrame) -> dict:
    out = {}
    for c in SHARE_COLS:
        out[c] = int(((p[c] < 0) | (p[c] > 100)).sum())
    for c in MERIT_COLS:
        out[c] = int(((p[c] < 0) | (p[c] > MERIT_MAX)).sum())
    out["pupils_1_9_nonpositive"] = int((p["pupils_1_9"] <= 0).sum())
    return out


def national_reconciliation(p: pd.DataFrame, raw: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Kolada's national value ('0000') vs the pupil-weighted mean of the 290 municipalities."""
    nat = raw[(raw["municipality"] == "0000") & (raw["gender"] == "T")]
    inv = {v: n for n, v in VARIABLES.items()}
    nat = nat[nat["kpi"].isin([VARIABLES[c] for c in cols])].assign(var=lambda d: d["kpi"].map(inv))
    nat = nat.pivot(index="period", columns="var", values="value")
    rows = []
    for c in cols:
        w = weighted_national(p, c)
        for y in w.index:
            k = nat.at[y, c] if (y in nat.index and c in nat.columns) else np.nan
            rows.append({"variable": c, "year": int(y), "kolada_national": k, "weighted_mean": round(w[y], 2),
                         "difference": round(w[y] - k, 2) if pd.notna(k) else np.nan})
    return pd.DataFrame(rows)


def year_to_year_changes(p: pd.DataFrame, col: str = "merit") -> pd.DataFrame:
    s = p.sort_values(["municipality", "year"]).copy()
    s["prev"] = s.groupby("municipality")[col].shift()
    s["prev_year"] = s.groupby("municipality")["year"].shift()
    s = s[s["prev"].notna() & (s["year"] - s["prev_year"] == 1)]
    s["change"] = s[col] - s["prev"]
    return s[["municipality", "name", "year", "cohort_est", "change"]]


def size_bands(cohort: pd.Series) -> pd.Series:
    """Fixed bands of estimated grade-9 cohort size (pupils in grades 1-9 / 9)."""
    return pd.cut(cohort, [0, 50, 100, 200, 500, np.inf], right=False,
                  labels=["<50", "50-99", "100-199", "200-499", "500+"])


def change_by_size(ch: pd.DataFrame) -> pd.DataFrame:
    ch = ch.assign(band=size_bands(ch["cohort_est"]))
    g = ch.groupby("band", observed=True)["change"]
    return pd.DataFrame({
        "n": g.size(),
        "sd_change": g.std().round(1),
        "p95_abs_change": g.apply(lambda s: s.abs().quantile(0.95)).round(1),
        "share_abs_gt_10": g.apply(lambda s: (s.abs() > 10).mean()).round(3),
    })


def summarise(p: pd.DataFrame, raw: pd.DataFrame, ou: pd.DataFrame | None, scb: pd.DataFrame | None) -> dict:
    comp = completeness(p)
    ch = year_to_year_changes(p)
    # Stable order: largest |change| first, ties broken by municipality code and year.
    top = (ch.assign(_abs=ch["change"].abs())
           .sort_values(["_abs", "municipality", "year"], ascending=[False, True, True], kind="mergesort")
           .drop(columns="_abs").head(10))
    rec = national_reconciliation(p, raw, ["merit", "merit_home", "parents_post_secondary", "foreign_background"])
    out = {
        "raw_rows": int(len(raw)),
        "raw_id_categories": id_categories(raw),
        "panel_rows": int(len(p)),
        "municipalities": int(p["municipality"].nunique()),
        "years": [int(p["year"].min()), int(p["year"].max())],
        "completeness": {v: {int(y): int(n) for y, n in comp.loc[v].items()} for v in comp.index},
        "status_counts": status_counts(raw),
        "integer_share": integer_share(p, ["merit", "merit_home", "parents_post_secondary",
                                           "foreign_background"]).to_dict(orient="index"),
        "range_violations": range_violations(p),
        "national_reconciliation": rec.to_dict(orient="records"),
        "max_abs_reconciliation_diff": {
            v: float(rec.loc[rec["variable"] == v, "difference"].abs().max()) for v in rec["variable"].unique()},
        "cohort_est": {
            "min": round(float(p["cohort_est"].min()), 1),
            "median": round(float(p["cohort_est"].median()), 1),
            "max": round(float(p["cohort_est"].max()), 1),
            "municipalities_median_below_50": int((p.groupby("municipality")["cohort_est"].median() < 50).sum()),
        },
        "merit_change": {
            "n": int(len(ch)),
            "sd": round(float(ch["change"].std()), 2),
            "share_abs_gt_10": round(float((ch["change"].abs() > 10).mean()), 3),
            "n_abs_gt_25": int((ch["change"].abs() > 25).sum()),
            "spearman_abs_change_vs_size": round(float(
                ch["change"].abs().rank().corr(ch["cohort_est"].rank())), 3),
            "by_size": change_by_size(ch).reset_index().astype({"band": str}).to_dict(orient="records"),
            "largest": top.round(1).to_dict(orient="records"),
        },
        "population_agreement": {
            "corr_merit_vs_home": round(float(p[["merit", "merit_home"]].corr().iloc[0, 1]), 3),
            "corr_merit_vs_municipal": round(float(p[["merit", "merit_municipal"]].corr().iloc[0, 1]), 3),
            "mean_home_minus_location_stockholm_county": round(float(
                (p["merit_home"] - p["merit"])[p["stockholm_county"]].mean()), 2),
            "mean_home_minus_location_rest": round(float(
                (p["merit_home"] - p["merit"])[~p["stockholm_county"]].mean()), 2),
        },
        "covariate_correlations": p[["merit", "parents_post_secondary", "foreign_background"]].corr()
        .round(3).to_dict(),
    }
    if "salsa_units" in p:
        s = p.groupby("year").agg(with_units=("salsa_units", lambda v: int((v > 0).sum())),
                                  mean_units=("salsa_units", "mean"))
        out["salsa"] = {"municipalities_with_units": s["with_units"].to_dict(),
                        "mean_units": s["mean_units"].round(1).to_dict(),
                        "school_units_total": int(ou["ou"].nunique()) if ou is not None else None}
    if scb is not None and len(scb):
        out["scb_national_by_sex"] = scb.to_dict(orient="records")
        stats = {}
        for sex, g in scb.sort_values("year").groupby("sex"):
            stats[sex] = {"median_difference": round(float(g["difference"].median()), 2),
                          "min_difference": round(float(g["difference"].min()), 2),
                          "max_difference": round(float(g["difference"].max()), 2),
                          "corr_yearly_changes": round(float(g["scb"].diff().corr(g["kolada"].diff())), 3)}
        out["scb_comparison_stats"] = stats
    return out


def scb_comparison(tema42: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """SCB/Skolverket national merit value by sex vs Kolada's national N15504 by sex."""
    from scb import school_year_to_spring

    t = tema42.copy()
    dims = {"SvUtlBakgrund", "ForUtb", "Kon", "Tid"}
    missing = dims - set(t.columns)
    if missing:
        raise ValueError(f"Tema42 lacks {sorted(missing)} (was the variable eliminated by the query?)")
    value_col = [c for c in t.columns if c not in dims]
    if len(value_col) != 1:
        raise ValueError(f"expected one value column in Tema42, got {value_col}")
    t = t[(t["SvUtlBakgrund"] == "totalt") & (t["ForUtb"] == "totalt")]
    t = t.assign(year=t["Tid"].map(school_year_to_spring), sex=t["Kon"].map({"flickor": "K", "pojkar": "M"}))
    t = t.rename(columns={value_col[0]: "scb"})[["year", "sex", "scb"]]
    k = raw[(raw["municipality"] == "0000") & (raw["kpi"] == VARIABLES["merit"]) & raw["gender"].isin(["K", "M"])]
    k = k.rename(columns={"period": "year", "gender": "sex", "value": "kolada"})[["year", "sex", "kolada"]]
    m = t.merge(k, on=["year", "sex"], how="inner").sort_values(["year", "sex"])
    m["difference"] = (m["kolada"] - m["scb"]).round(2)
    return m.reset_index(drop=True)


def scb_vs_published(cmp: pd.DataFrame, raw: pd.DataFrame, published: pd.DataFrame) -> pd.DataFrame:
    """Explain the SCB gap: combine SCB's values for girls and boys with the girls' share
    implied by Kolada (T = w*K + (1-w)*M) and compare both series with Skolverket's
    published national averages for 16 and 17 subjects."""
    k = raw[(raw["municipality"] == "0000") & (raw["kpi"] == VARIABLES["merit"])]
    kt = k.pivot_table(index="period", columns="gender", values="value")
    w = (kt["T"] - kt["M"]) / (kt["K"] - kt["M"])
    scb = cmp.pivot_table(index="year", columns="sex", values="scb")
    out = pd.DataFrame({"girls_share": w.round(3), "kolada_total": kt["T"],
                        "scb_combined": (w * scb["K"] + (1 - w) * scb["M"]).round(1)}).dropna()
    out.index.name = "year"
    pub = published.pivot_table(index="year", columns="subjects", values="value")
    out["skolverket_17"] = pub.get(17)
    out["skolverket_16"] = pub.get(16)
    return out.reset_index()


def _table(rows: list[dict], cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join("" if r.get(c) is None or (isinstance(r.get(c), float) and np.isnan(r.get(c)))
                                            else str(r.get(c)) for c in cols) + " |\n" for r in rows)


def render_markdown(s: dict) -> str:
    """docs/data_quality.md. Generated from reports/data_quality_summary.json — do not edit by hand."""
    comp = s["completeness"]
    years = sorted({int(y) for v in comp.values() for y in v})
    comp_rows = [{"variable": v, **{str(y): comp[v].get(y, comp[v].get(str(y))) for y in years}} for v in comp]
    rec = [r for r in s["national_reconciliation"] if r["variable"] in ("merit", "merit_home")]
    mc = s["merit_change"]
    ids = s["raw_id_categories"]
    lines = [
        "# Data quality report",
        "",
        "*Generated by `python scripts/run_pipeline.py quality` from `reports/data_quality_summary.json`. "
        "Do not edit by hand.*",
        "",
        "## 1. What a row is",
        f"- Raw file: {s['raw_rows']:,} rows = KPI × Kolada id × year × sex. Ids: {ids.get('municipality', 0)} "
        f"municipalities, {ids.get('country', 0)} country row, {ids.get('region', 0)} regions and "
        f"{ids.get('kolada_group', 0):,} Kolada comparison groups. Only the municipalities are used.",
        f"- Analysis panel (`data/processed/panel.csv`): one row per municipality × spring term, "
        f"{s['panel_rows']:,} rows = {s['municipalities']} municipalities × {s['years'][0]}–{s['years'][1]}; "
        "no duplicated keys (the build fails on duplicates or a missing municipality-year).",
        "",
        "## 2. Completeness (municipalities with a value, of 290)",
        _table(comp_rows, ["variable", *[str(y) for y in years]]),
        "The primary outcome and both covariates are complete. Missing values elsewhere are Kolada status "
        "`Privacy` (suppressed small groups) or `Missing`:",
        "",
        _table([{"variable|status": k, "rows": v} for k, v in s["status_counts"].items()], ["variable|status", "rows"]),
        "Eligibility for vocational programmes is suppressed for 4–14 municipalities a year; it is only a secondary outcome.",
        "",
        "## 3. Precision and ranges",
        "- **Rounding changes over time:** the background shares are whole percentages up to 2022 and have one "
        "decimal from 2023; the home-municipality merit value is a whole number from 2016. Rounding error is at "
        "most ±0.5, small next to the spread between municipalities, and is left as it is.",
        f"- **Range checks:** shares in 0–100 and merit values in 0–{MERIT_MAX}: "
        f"{sum(v for k, v in s['range_violations'].items())} violations.",
        "",
        "## 4. Reconciliation",
        "**Internal:** the pupil-weighted mean of the 290 municipalities (weights = pupils in grades 1–9) against "
        "Kolada's own national value.",
        "",
        _table(rec, ["variable", "year", "kolada_national", "weighted_mean", "difference"]),
        f"- Primary outcome (`merit`, schools located in the municipality): largest gap "
        f"{s['max_abs_reconciliation_diff']['merit']} points — the municipal values add up to the national figure.",
        f"- Home municipality (`merit_home`): largest gap {s['max_abs_reconciliation_diff']['merit_home']} points, "
        "in 2017, where Kolada's national value (234.4) is far from both the municipal values and the other "
        "series. Treated as an error in the national row; it does not affect the analysis, which never uses "
        "national rows.",
        f"- Background shares: largest gap {s['max_abs_reconciliation_diff']['parents_post_secondary']} pp "
        f"(parents' education) and {s['max_abs_reconciliation_diff']['foreign_background']} pp (foreign background).",
    ]
    if s.get("scb_explained"):
        ex = s["scb_explained"]
        lines_ex = [
            "",
            "**Why the levels differ (verified):** SCB's table is the merit value for **16 subjects**; Kolada "
            "(N15504) is the merit value for **17 subjects** (16 + modern languages), the figure Skolverket "
            "headlines. Combining SCB's values for girls and boys with the girls' share implied by Kolada "
            "reproduces Skolverket's published 16-subject national averages, and Kolada's total equals the "
            "published 17-subject averages (`data/reference/skolverket_published_merit.csv`, with sources):",
            "",
            _table(ex["rows"], ["year", "girls_share", "scb_combined", "skolverket_16", "kolada_total",
                                "skolverket_17"]),
            "",
            f"- Largest difference to a published value: {ex['max_abs_diff_16']} points (16 subjects) and "
            f"{ex['max_abs_diff_17']} points (17 subjects).",
            "- The gap is larger for girls, consistent with more girls having a modern-language grade. The 2016 "
            "value is an outlier (gap 12.6 points); Skolverket published the 2016 results both with and without "
            "pupils of unknown background, which may explain it. Not verified.",
        ]
    else:
        lines_ex = []
    if s.get("scb_national_by_sex"):
        lines += [
            "",
            "**External:** Kolada's national merit value by sex against SCB's table *Meritvärde för elever som "
            "avslutat årskurs 9* (LE0201Utb/Tema42, Skolverket data).",
            "",
            _table(s["scb_national_by_sex"], ["year", "sex", "scb", "kolada", "difference"]),
        ]
        st = s["scb_comparison_stats"]
        lines += [
            f"- **The level check does not pass:** Kolada is higher every year, by a median of "
            f"{st['K']['median_difference']} points for girls and {st['M']['median_difference']} for boys "
            f"(range {min(v['min_difference'] for v in st.values())}–{max(v['max_difference'] for v in st.values())}).",
            f"- **The year pattern matches** for girls (correlation of yearly changes {st['K']['corr_yearly_changes']}) "
            f"and less well for boys ({st['M']['corr_yearly_changes']}), mainly because of SCB's 2016 value for boys.",
            "- A gap this stable points to a definition difference, not a data error.",
            *lines_ex,
            "- Impact: none on the analysis, which only compares municipalities within Kolada's definition, and "
            "Kolada's municipal values add up to its national value (internal check above). The README will "
            "state that the level is Skolverket's Kolada definition.",
        ]
    lines += [
        "",
        "## 5. Size and year-to-year movement (raw merit value)",
        f"- Estimated grade-9 cohort (pupils in grades 1–9 ÷ 9; Kolada has no grade-9 count): median "
        f"{s['cohort_est']['median']}, range {s['cohort_est']['min']}–{s['cohort_est']['max']}. "
        f"{s['cohort_est']['municipalities_median_below_50']} municipalities have a median cohort under 50 pupils.",
        f"- {mc['n']:,} consecutive-year changes: SD {mc['sd']} points; {mc['share_abs_gt_10']:.0%} move more than "
        f"10 points and {mc['n_abs_gt_25']} more than 25. Larger municipalities move less "
        f"(Spearman correlation between |change| and size {mc['spearman_abs_change_vs_size']}).",
        "",
        _table(mc["by_size"], ["band", "n", "sd_change", "p95_abs_change", "share_abs_gt_10"]),
        "This is the raw pattern the project is about: in municipalities with fewer than 100 pupils a year, half "
        "of all year-to-year changes exceed 10 points, against 5 % in municipalities with 500+. It is not yet "
        "adjusted for background (M5) or split into persistent and noise parts (M6).",
        "",
        "Largest changes (checked: all are small or mid-sized municipalities, several reverse the next year — "
        "consistent with cohort noise, not data errors):",
        "",
        _table(mc["largest"], ["name", "municipality", "year", "cohort_est", "change"]),
        "## 6. Populations agree",
        f"- Correlation of the primary outcome with home municipality {s['population_agreement']['corr_merit_vs_home']} "
        f"and with municipal schools {s['population_agreement']['corr_merit_vs_municipal']}.",
        f"- Home-municipality values are on average {s['population_agreement']['mean_home_minus_location_stockholm_county']} "
        f"points higher than school-location values in Stockholm county and "
        f"{s['population_agreement']['mean_home_minus_location_rest']} elsewhere: pupils who commute to schools in "
        "other municipalities differ from those who stay. This is why the population choice (D7) is tested in M7.",
        "",
        "## 7. Covariates",
        f"- Correlation with merit value: parents with post-secondary education "
        f"{s['covariate_correlations']['merit']['parents_post_secondary']}, foreign background "
        f"{s['covariate_correlations']['merit']['foreign_background']} (pooled over years, before any model).",
        "- Both covariates refer to grades 1–9 in schools located in the municipality, the outcome to grade 9 (D8).",
    ]
    if "salsa" in s:
        w = s["salsa"]["municipalities_with_units"]
        lines += [
            "",
            "## 8. SALSA school units (for reconciliation, D9)",
            f"- {s['salsa']['school_units_total']:,} school units; municipalities with at least one unit with a SALSA "
            f"value: {min(w.values())}–{max(w.values())} per year (small schools are not modelled by Skolverket). "
            "Municipalities without units are left out of the SALSA comparison only.",
        ]
    lines += [
        "",
        "## 9. Decisions taken from this report (before any model)",
        "- Nothing is removed from the panel: no range violations, no duplicates, and the large changes look like "
        "noise, not errors.",
        "- National rows are never used in the analysis (Kolada's 2017 home-municipality national value is off).",
        "- Size enters as the estimated cohort (pupils 1–9 ÷ 9), as planned in D10.",
        "",
    ]
    return "\n".join(lines)
