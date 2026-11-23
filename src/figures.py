"""Static figures for the README (matplotlib; maps need geopandas).

Palette and chrome follow one light theme: blue for data, gray for noise bands,
a blue <-> red diverging scale with a gray midpoint for above/below-expected maps.
Titles state the conclusion; source lines name Kolada / SCB.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
BAND = "#e9e8e2"
SEQ_BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV_NEG, DIV_MID, DIV_POS = "#e34948", "#f0efec", "#2a78d6"  # below expected / neutral / above
SOURCE = "Source: Kolada (Skolverket data); SCB. Merit value = grade 9, 17 subjects, schools located in the municipality."


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    })


def _finish(fig, path, source=SOURCE):
    fig.text(0.01, -0.02, source, fontsize=7.5, color=MUTED, ha="left", va="top")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def changes_vs_size(ch, a, b, path, title, z=1.959964):
    """Signed one-year change (year-demeaned) vs cohort size with the fitted 95 % noise band."""
    style()
    fig, ax = plt.subplots(figsize=(8, 4.6))
    n = np.geomspace(max(15, ch["cohort_est"].min() * 0.9), ch["cohort_est"].max() * 1.1, 200)
    band = z * np.sqrt(a + b / n)
    ax.fill_between(n, -band, band, color=BAND, lw=0, label="95 % range expected from cohort noise")
    ax.scatter(ch["cohort_est"], ch["change_dm"], s=9, color=BLUE, alpha=0.35, lw=0,
               label="one municipality, one year")
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks([25, 50, 100, 200, 500, 1000, 3000, 10000])
    ax.set_xticklabels(["25", "50", "100", "200", "500", "1k", "3k", "10k"])
    ax.set_xlabel("Grade-9 pupils per year (estimated, log scale)")
    ax.set_ylabel("Change in merit value vs previous year\n(points, national change removed)")
    ax.set_title(title)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    _finish(fig, path)


def funnel_plot(f, year, path):
    style()
    fig, ax = plt.subplots(figsize=(8, 4.6))
    f = f.sort_values("cohort_est")
    ax.fill_between(f["cohort_est"], -f["limit95"], f["limit95"], color=BAND, lw=0,
                    label="95 % limits if differences were only cohort noise")
    ax.plot(f["cohort_est"], f["limit998"], color=MUTED, lw=1, ls="--", label="99.8 % limits")
    ax.plot(f["cohort_est"], -f["limit998"], color=MUTED, lw=1, ls="--")
    ax.scatter(f["cohort_est"], f["deviation"], s=14, color=BLUE, alpha=0.7, lw=0, label="municipality")
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks([25, 50, 100, 200, 500, 1000, 3000, 10000])
    ax.set_xticklabels(["25", "50", "100", "200", "500", "1k", "3k", "10k"])
    ax.set_xlabel("Grade-9 pupils per year (estimated, log scale)")
    ax.set_ylabel(f"Merit value {year} minus national mean (points)")
    out = int(f["outside95"].sum())
    ax.set_title(f"{out} of {len(f)} municipalities differ from the national mean by more than noise ({year})")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    _finish(fig, path)


def choropleth(gdf, col, path, title, cmap_colors=SEQ_BLUES, label="", inset_county="01", diverging=False,
               vlim=None):
    """Sweden + Stockholm-county panel. `gdf` has columns kommun, geometry and `col`."""
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm, Normalize

    style()
    if diverging:
        cmap = LinearSegmentedColormap.from_list("div", [DIV_NEG, DIV_MID, DIV_POS])
        v = vlim or float(np.nanmax(np.abs(gdf[col])))
        norm = TwoSlopeNorm(vmin=-v, vcenter=0, vmax=v)
    else:
        cmap = LinearSegmentedColormap.from_list("seq", cmap_colors)
        lo, hi = vlim or (float(np.nanpercentile(gdf[col], 2)), float(np.nanpercentile(gdf[col], 98)))
        norm = Normalize(vmin=lo, vmax=hi)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 7.5), gridspec_kw={"width_ratios": [1.05, 1]})
    for ax, data in ((ax1, gdf), (ax2, gdf[gdf["kommun"].str[:2] == inset_county])):
        data.plot(column=col, cmap=cmap, norm=norm, ax=ax, edgecolor=SURFACE, linewidth=0.3,
                  missing_kwds={"color": "#d9d8d2"})
        ax.set_axis_off()
    ax2.set_title("Stockholm county", fontsize=10, color=INK2, loc="left", fontweight="normal")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=[ax1, ax2], orientation="horizontal", fraction=0.035, pad=0.03, aspect=40)
    cb.set_label(label, color=INK2)
    cb.outline.set_visible(False)
    fig.suptitle(title, x=0.02, ha="left", fontsize=12, fontweight="bold")
    _finish(fig, path)


def actual_vs_expected(d, year, path, title, highlight_county="01"):
    style()
    s = d[d["year"] == year]
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    hi = s["county"] == highlight_county
    lo, up = float(min(s["expected"].min(), s["merit"].min())) - 3, float(max(s["expected"].max(), s["merit"].max())) + 3
    ax.plot([lo, up], [lo, up], color=AXIS, lw=1, zorder=1)
    ax.scatter(s.loc[~hi, "expected"], s.loc[~hi, "merit"], s=16, color=BLUE, alpha=0.6, lw=0,
               label="other municipalities", zorder=2)
    ax.scatter(s.loc[hi, "expected"], s.loc[hi, "merit"], s=26, color=ORANGE, lw=0.6, edgecolor=SURFACE,
               label="Stockholm county", zorder=3)
    ax.text(up - 1, up - 4, "actual = expected", color=MUTED, fontsize=8, ha="right", va="top", rotation=0)
    ax.set_xlim(lo, up)
    ax.set_ylim(lo, up)
    ax.set_xlabel(f"Expected merit value {year} from pupil background (points)")
    ax.set_ylabel(f"Actual merit value {year} (points)")
    ax.set_title(title, fontsize=11)
    ax.legend(frameon=False, loc="upper left", fontsize=8.5)
    _finish(fig, path)


def caterpillar(eff, path, title):
    """Every municipality's persistent effect with its 95 % interval, sorted."""
    style()
    e = eff.sort_values("eb_mean").reset_index(drop=True)
    colors = np.where(e["verdict"] == "above", DIV_POS, np.where(e["verdict"] == "below", DIV_NEG, "#b5b4ad"))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(len(e))
    ax.vlines(x, e["lo95"], e["hi95"], colors=colors, lw=1.1, alpha=0.9)
    ax.scatter(x, e["eb_mean"], s=7, c=colors, zorder=3, lw=0)
    ax.axhline(0, color=INK2, lw=0.8)
    n_above, n_below = int((e["verdict"] == "above").sum()), int((e["verdict"] == "below").sum())
    ax.text(len(e) - 2, float(e["hi95"].max()), f"{n_above} clearly above expected", color=DIV_POS,
            ha="right", va="top", fontsize=9)
    ax.text(2, float(e["lo95"].min()), f"{n_below} clearly below expected", color=DIV_NEG, ha="left",
            va="bottom", fontsize=9)
    ax.text(len(e) / 2, float(e["hi95"].max()), f"{len(e) - n_above - n_below} interval includes 0",
            color=INK2, ha="center", va="top", fontsize=9)
    ax.set_xticks([])
    ax.set_xlabel("290 municipalities, sorted by estimated persistent effect")
    ax.set_ylabel("Persistent difference from expected\nmerit value (points, 95 % interval)")
    ax.set_title(title)
    ax.grid(axis="x", visible=False)
    _finish(fig, path)


def rank_ranges(eff, path, title, county="01"):
    """Rank intervals (1 = furthest above expected among all 290) for one county."""
    style()
    e = eff[eff["county"] == county].sort_values("rank_point", ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 0.28 * len(e) + 1.6))
    y = np.arange(len(e))
    colors = np.where(e["verdict"] == "above", DIV_POS, np.where(e["verdict"] == "below", DIV_NEG, "#8f8e87"))
    ax.hlines(y, e["rank_lo"], e["rank_hi"], colors=colors, lw=3, alpha=0.55)
    ax.scatter(e["rank_point"], y, s=22, c=colors, zorder=3, lw=0)
    ax.set_yticks(y)
    ax.set_yticklabels(e["name"], fontsize=8.5, color=INK2)
    ax.set_xlim(0, len(eff) + 5)
    ax.set_xlabel(f"Rank among all {len(eff)} municipalities (1 = furthest above expected), 95 % interval")
    ax.set_title(title, fontsize=11)
    ax.grid(axis="y", visible=False)
    _finish(fig, path, source=SOURCE + " Rank intervals simulated from the model.")


def robustness_bars(rows, path, title):
    """Municipalities clearly below (left) / above (right) expected under each specification."""
    style()
    rows = list(rows)[::-1]
    fig, ax = plt.subplots(figsize=(8.4, 0.42 * len(rows) + 1.4))
    y = np.arange(len(rows))
    below = np.array([r["below"] for r in rows])
    above = np.array([r["above"] for r in rows])
    ax.barh(y, -below, color=DIV_NEG, height=0.6, edgecolor=SURFACE, linewidth=1)
    ax.barh(y, above, color=DIV_POS, height=0.6, edgecolor=SURFACE, linewidth=1)
    for yi, b, a, r in zip(y, below, above, rows):
        ax.text(-b - 2, yi, str(b), va="center", ha="right", fontsize=8.5, color=INK2)
        ax.text(a + 2, yi, f"{a}   (ρ = {r['spearman_with_primary']:.2f})", va="center", ha="left",
                fontsize=8.5, color=INK2)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([r["variant"] for r in rows], fontsize=9, color=INK2)
    lim = max(below.max(), above.max()) + 45
    ax.set_xlim(-lim + 25, lim)
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlabel("municipalities clearly below expected  ←   |   →  clearly above expected "
                  "(ρ = rank correlation with primary)", fontsize=8.5)
    ax.set_title(title, fontsize=11)
    _finish(fig, path)
