"""Recompute the numbers quoted in README.md from reports/*.json and fail if one is missing.

Usage: python scripts/check_readme.py   (also run by tests/test_readme_numbers.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load(name):
    return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))


def _m(x: float, fmt: str) -> str:
    """Format with a typographic minus, as in the README."""
    return format(x, fmt).replace("-", "\u2212")


def expected_strings() -> list[tuple[str, str]]:
    import models

    q, d, e = _load("data_quality_summary.json"), _load("descriptives.json"), _load("expected_value.json")
    p, r = _load("persistence.json"), _load("robustness.json")
    h, sd = p["homoskedastic"], p["size_dependent"]
    fb = e["coefficients_linear"]["foreign_background"]
    v = {x["variant"]: x for x in r["variants"]}
    others = [x for x in r["variants"] if x["variant"] != "primary"]
    n_diff = [x["above"] + x["below"] for x in r["variants"]]
    rho = [x["spearman_with_primary"] for x in others]
    st = [int(x["stockholm_county_above"].split("/")[0]) for x in r["variants"]]
    obs = {b["band"]: b["observed_p95_abs_change"] for b in p["change_check_by_size"]}
    rel = sd["reliability_1y_by_cohort"]
    rel3 = sd["reliability_3y_by_cohort"]
    med = q["cohort_est"]["median"]
    tau2 = sd["tau"] ** 2
    sig_med = models.sigma2_of_n(med, sd["c"], sd["d"])
    out = [
        ("panel rows", f"{q['panel_rows']:,} municipality-years"),
        ("within-year R2", f"explains {e['within_year_r2_chosen'] * 100:.0f} % of the differences"),
        ("foreign background coef", f"({_m(fb['coef'], '.3f')} points per percentage point, CI {_m(fb['ci95'][0], '.2f')} to {_m(fb['ci95'][1], '.2f')})"),
        ("icc headline", f"A single year is {h['icc'] * 100:.0f} % signal"),
        ("tau", f"has SD {sd['tau']:.1f} points"),
        ("sigma", f"noise has SD {h['sigma']:.1f}"),
        ("icc ci", f"**{h['icc']:.2f} (CI {h['bootstrap_ci95']['icc'][0]:.2f}–{h['bootstrap_ci95']['icc'][1]:.2f})**"),
        ("rel 30", f"**{rel['30']:.2f}** for 30 pupils"),
        ("rel 100", f"**{rel['100']:.2f}** for 100"),
        ("rel 200", f"**{rel['200']:.2f}** for 200"),
        ("rel 1000", f"**{rel['1000']:.2f}** for 1,000"),
        ("rel3", f"{rel3['30']:.2f} / {rel3['100']:.2f} / {rel3['200']:.2f} / {rel3['1000']:.2f}"),
        ("n differ", f"**{sd['verdicts']['above'] + sd['verdicts']['below']} of 290**"),
        ("above", f"above ({sd['verdicts']['above']})"),
        ("below", f"below ({sd['verdicts']['below']})"),
        ("chance", f"~{round(p['expected_false_positives_if_no_differences'])} that chance"),
        ("not distinguishable", f"The other {sd['verdicts']['not distinguishable']} cannot"),
        ("rank width", f"spans **{p['rank_interval_width_median']} places** (IQR "
                       f"{p['rank_interval_width_quartiles'][0]}–{p['rank_interval_width_quartiles'][1]})"),
        ("top decile overlap", f"only **{p['top_decile_last_year_also_eb_top_decile'].split('/')[0]}** are in the persistent top 10 %"),
        ("stockholm", f"**{v['primary']['stockholm_county_above'].split('/')[0]} of 26**"),
        ("stockholm range", f"{min(st)}–{max(st)} of 26 in every robustness variant"),
        ("moran", f"Moran's I **{r['morans_i']['persistent_effect_primary']['I']:.2f}**"),
        ("robust count", f"{min(n_diff)}–{max(n_diff)} municipalities differ persistently"),
        ("robust rho", f"correlate {min(rho):.2f}–1.00 with the primary"),
        ("threshold <50", f"| under 50 | ±{obs['<50']:.0f} points |"),
        ("threshold 50-99", f"| 50–99 | ±{obs['50-99']:.0f} points |"),
        ("threshold 100-199", f"| 100–199 | ±{obs['100-199']:.0f} points |"),
        ("threshold 200-499", f"| 200–499 | ±{obs['200-499']:.0f} points |"),
        ("threshold 500+", f"| 500+ | ±{obs['500+']:.0f} points |"),
        ("typical size", f"about {med:.0f} pupils a year"),
        ("typical reliability", f"from {tau2 / (tau2 + sig_med):.2f} for one year to {3 * tau2 / (3 * tau2 + sig_med):.2f}"),
        ("reconciliation", f"within {q['max_abs_reconciliation_diff']['merit']} points"),
        ("rank stability", f"(Spearman {d['rank_stability_range'][0]:.2f}–{d['rank_stability_range'][1]:.2f})"),
        ("salsa", f"expected values correlate {e['salsa']['corr_expected']:.2f}, residuals {e['salsa']['corr_resid_vs_salsa_deviation']:.2f}"),
        ("autocorr", f"({p['lag1_autocorr_within_residual']:.2f})"),
        ("school units", "4,564 school units"),
    ]
    return out


def main() -> int:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [(k, s) for k, s in expected_strings() if s not in text]
    for k, s in missing:
        print(f"MISSING [{k}]: {s}")
    print(f"{len(expected_strings()) - len(missing)}/{len(expected_strings())} README numbers match reports/")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
