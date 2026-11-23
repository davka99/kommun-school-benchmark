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
