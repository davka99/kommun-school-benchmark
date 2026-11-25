"""Pipeline entry point. Usage: python scripts/run_pipeline.py <stage> [<stage> ...]

Stages
  probe  Verify the sources before any full fetch (M1). Detects the Kolada API
         version, lists candidate KPIs for the search terms in config.py, checks
         municipality coverage of every grade-9 candidate for config.PROBE_YEAR,
         lists the municipality register, and finds, downloads and dissolves SCB's
         DeSO layer to municipalities. Writes data/raw/_probe/ and, if the geodata
         works, data/raw/geo/kommuner.geojson. Every check is recorded in
         data/raw/_probe/probe_report.json; the stage fails if a critical check fails.

  probe_scb  M2. Walks SCB's PxWeb tree for grade-9 tables (background by home
         municipality, cohort counts) and records their variables.
  fetch  M2. Every KPI in config.FETCH_KPIS for config.YEARS, all genders, to
         data/raw/kolada/kolada_long.csv.gz (+ fetch_manifest.json), and
         school-unit SALSA values with their municipality to salsa_school_units.csv.gz.

  reconcile  M3. SCB table Tema42 (national grade-9 merit value by sex) to
         data/raw/scb/ for an external check of Kolada's national values.
  quality  M3, offline. data/processed/panel.csv (290 municipalities x years),
         reports/data_quality_summary.json and docs/data_quality.md.

  descriptives  M4, offline. Rank stability, top/bottom churn, cohort-noise model
         (change^2 = a + b/n), funnel limits; reports/descriptives.json + figures.

  expected  M5. OLS expected value (D8; D11 functional-form rule), diagnostics,
         SALSA reconciliation: reports/expected_value.json, data/processed/expected_values.csv.
  persistence  M6. Random-intercept model, size-dependent noise, empirical-Bayes
         effects, rank intervals, decision thresholds: reports/persistence.json,
         reports/municipality_effects.csv and figures.

  robustness  M7. Pre-registered robustness variants, Stockholm-county table,
         Moran's I: reports/robustness.json, robustness_effects.csv, stockholm_county.csv.

  bi  Offline. SQLite star schema + SQL views (sql/), exported to reports/bi/ for the
         Power BI report described in docs/powerbi.md.

Network access is only needed for `probe`, `probe_scb`, `fetch` and `reconcile`. The build
sandbox cannot reach the sources, so these stages run in GitHub Actions.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
import kolada  # noqa: E402


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _detect_base(get) -> tuple[str, dict]:
    tried = {}
    for base in config.KOLADA_BASES:
        url = kolada.kpi_search_url(base, "meritvärde")
        try:
            payload = get(url)
            if isinstance(payload, dict) and "values" in payload:
                tried[base] = {"ok": True, "top_level_keys": sorted(payload)}
                return base, tried
            tried[base] = {"ok": False, "top_level_keys": sorted(payload) if isinstance(payload, dict) else str(type(payload))}
        except Exception as exc:  # noqa: BLE001
            tried[base] = {"ok": False, "error": str(exc)[:300]}
    raise RuntimeError(f"no Kolada API version answered: {tried}")


def stage_probe() -> None:
    import pandas as pd
    import requests

    out = config.PROBE_DIR
    out.mkdir(parents=True, exist_ok=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "checks": {}}
    critical_failed = []

    def check(name, critical=True):
        def deco(fn):
            try:
                report["checks"][name] = {"ok": True, **(fn() or {})}
            except Exception as exc:  # noqa: BLE001
                report["checks"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800],
                                          "trace": traceback.format_exc()[-1500:]}
                if critical:
                    critical_failed.append(name)
            return fn
        return deco

    get = kolada.make_getter(timeout=config.HTTP_TIMEOUT, user_agent=config.USER_AGENT)
    state = {}

    @check("kolada_api_version")
    def _():
        base, tried = _detect_base(get)
        state["base"] = base
        return {"base": base, "tried": tried}

    @check("kpi_search")
    def _():
        frames, per_term = [], {}
        for term in config.KPI_SEARCH_TERMS:
            df = kolada.parse_kpis(kolada.paginate(kolada.kpi_search_url(state["base"], term), get))
            df["search_term"] = term
            per_term[term] = len(df)
            frames.append(df)
        kpis = pd.concat(frames).drop_duplicates("id").sort_values("id")
        kpis.to_csv(out / "kpi_candidates.csv", index=False)
        state["kpis"] = kpis
        # Raw record of one KPI so field names can be checked by eye.
        first = get(kolada.kpi_search_url(state["base"], "meritvärde"))
        _write_json(out / "kpi_sample_record.json", first["values"][:2])
        return {"hits_per_term": per_term, "n_unique_kpis": int(len(kpis))}

    @check("grade9_coverage")
    def _():
        cand = kolada.grade9_candidates(state["kpis"], config.GRADE9_MARKERS)
        cand = cand.head(config.MAX_COVERAGE_CHECKS)
        cov_frames, errors = [], {}
        sample_written = False
        for kpi_id in cand["id"]:
            try:
                url = kolada.data_url(state["base"], [kpi_id], [config.PROBE_YEAR - 9, config.PROBE_YEAR])
                pages = list(kolada.paginate(url, get))
                if not sample_written and pages and pages[0]["values"]:
                    _write_json(out / "data_sample_record.json", pages[0]["values"][:3])
                    sample_written = True
                cov_frames.append(kolada.coverage(kolada.parse_data(pages)))
            except Exception as exc:  # noqa: BLE001
                errors[kpi_id] = str(exc)[:300]
        cov = pd.concat(cov_frames) if cov_frames else pd.DataFrame()
        if not cov.empty:
            cov = cov.merge(cand[["id", "title"]], left_on="kpi", right_on="id", how="left").drop(columns="id")
        cov.to_csv(out / "kpi_coverage.csv", index=False)
        return {"n_candidates": int(len(cand)), "n_checked": int(cov["kpi"].nunique()) if not cov.empty else 0,
                "errors": errors}

    @check("priority_coverage")
    def _():
        # One request per KPI for the whole window; coverage per KPI x year, both
        # sexes combined, with ranges for unit checks. No model or residual (D4).
        titles = state["kpis"].set_index("id")["title"].to_dict()
        frames, errors = [], {}
        for kpi_id in config.PRIORITY_KPIS:
            try:
                url = kolada.data_url(state["base"], [kpi_id], config.YEARS)
                frames.append(kolada.coverage(kolada.parse_data(kolada.paginate(url, get))))
            except Exception as exc:  # noqa: BLE001
                errors[kpi_id] = str(exc)[:300]
        cov = pd.concat(frames) if frames else pd.DataFrame(columns=["kpi"])
        cov["title"] = cov["kpi"].map(titles)
        cov.to_csv(out / "priority_coverage.csv", index=False)
        wide = cov.pivot_table(index="kpi", columns="period", values="n_values", aggfunc="first")
        wide.to_csv(out / "priority_coverage_wide.csv")
        missing = sorted(set(config.PRIORITY_KPIS) - set(cov["kpi"]))
        return {"n_kpis_with_data": int(cov["kpi"].nunique()), "kpis_without_data": missing, "errors": errors}

    @check("municipality_register")
    def _():
        from municipalities import is_kommun

        m = kolada.parse_municipalities(kolada.paginate(kolada.municipality_url(state["base"]), get))
        m.to_csv(out / "municipalities.csv", index=False)
        n_k = int(m["id"].map(is_kommun).sum())
        if n_k != config.N_MUNICIPALITIES:
            raise AssertionError(f"{n_k} kommun codes in the register, expected {config.N_MUNICIPALITIES}")
        return {"n_records": int(len(m)), "n_kommun": n_k, "types": m["type"].value_counts().to_dict()}

    @check("geodata")
    def _():
        import geopandas as gpd

        from geo import (dissolve_to_kommun, find_download_links, pick_deso_layer, rank_deso_links,
                         wfs_feature_types, wfs_getfeature_url)
        from municipalities import is_kommun

        s = requests.Session()
        s.headers["User-Agent"] = config.USER_AGENT
        links, page_errors = [], {}
        for page in config.SCB_DESO_PAGES:
            try:
                r = s.get(page, timeout=config.HTTP_TIMEOUT)
                r.raise_for_status()
                links += [u for u in find_download_links(r.text, page) if u not in links]
            except Exception as exc:  # noqa: BLE001
                page_errors[page] = str(exc)[:300]
        ranked = rank_deso_links(links)
        config.TMP.mkdir(parents=True, exist_ok=True)
        source, gdf, tried = None, None, {}
        for url in ranked[:4]:
            try:
                r = s.get(url, timeout=300)
                r.raise_for_status()
                fname = config.TMP / url.rsplit("/", 1)[-1].split("?")[0]
                fname.write_bytes(r.content)
                raw = gpd.read_file(fname)
                code_col = next(c for c in raw.columns if c.lower() in ("deso", "desokod", "deso_kod"))
                gdf = dissolve_to_kommun(raw, code_col)
                source = {"url": url, "n_deso": int(len(raw)), "crs": str(raw.crs), "columns": list(raw.columns)}
                break
            except Exception as exc:  # noqa: BLE001
                tried[url] = str(exc)[:300]
        if gdf is None:
            # SCB's WFS: find the most recent DeSO layer and dissolve it.
            try:
                r = s.get(f"{config.SCB_WFS}?service=WFS&request=GetCapabilities", timeout=config.HTTP_TIMEOUT)
                r.raise_for_status()
                layers = wfs_feature_types(r.text)
                (out / "scb_wfs_layers.txt").write_text("\n".join(layers) + "\n", encoding="utf-8")
                layer = pick_deso_layer(layers)
                if layer is None:
                    raise RuntimeError(f"no DeSO layer among {len(layers)} WFS layers")
                r = s.get(wfs_getfeature_url(config.SCB_WFS, layer), timeout=600)
                r.raise_for_status()
                fname = config.TMP / "deso_wfs.geojson"
                fname.write_bytes(r.content)
                raw = gpd.read_file(fname)
                code_col = next(c for c in raw.columns if c.lower() in ("deso", "desokod", "deso_kod"))
                gdf = dissolve_to_kommun(raw, code_col)
                source = {"url": f"{config.SCB_WFS} layer {layer}", "n_deso": int(len(raw)),
                          "crs": str(raw.crs), "columns": list(raw.columns)}
            except Exception as exc:  # noqa: BLE001
                tried["scb_wfs"] = str(exc)[:500]
        if gdf is None:
            raw = gpd.read_file(config.GEO_FALLBACK_URL)
            code_col = next(c for c in raw.columns if c.lower() in ("kom_kod", "kommunkod", "id", "kod"))
            raw["kommun"] = raw[code_col].astype(str).str.zfill(4)
            gdf = raw[["kommun", "geometry"]]
            source = {"url": config.GEO_FALLBACK_URL, "fallback": True, "crs": str(raw.crs),
                      "columns": list(raw.columns)}
        n_k = int(gdf["kommun"].map(is_kommun).sum())
        g = gdf.to_crs(3006)
        g["geometry"] = g.geometry.simplify(config.GEO_SIMPLIFY_M)
        geo_dir = config.RAW / "geo"
        geo_dir.mkdir(parents=True, exist_ok=True)
        g.to_crs(4326).to_file(geo_dir / "kommuner.geojson", driver="GeoJSON")
        if n_k != config.N_MUNICIPALITIES:
            raise AssertionError(f"{n_k} municipalities in the geodata, expected {config.N_MUNICIPALITIES}")
        return {"links_found": links, "page_errors": page_errors, "download_errors": tried, "source": source,
                "n_kommun": n_k}

    report["critical_failed"] = critical_failed
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(out / "probe_report.json", report)
    print(json.dumps({k: v.get("ok") for k, v in report["checks"].items()}, indent=2))
    if critical_failed:
        raise SystemExit(f"probe: critical checks failed: {critical_failed}")


def _write_csv_gz(df, path: Path) -> None:
    """Deterministic gzip (fixed header time) so reruns give identical files."""
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
        gz.write(df.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def stage_probe_scb() -> None:
    """M2: look for grade-9 background by home municipality and grade-9 counts in SCB's database."""
    import scb

    get = kolada.make_getter(timeout=config.HTTP_TIMEOUT, user_agent=config.USER_AGENT)
    out = config.PROBE_DIR
    tables, errors = scb.browse(get, config.SCB_START_PATHS, config.SCB_TABLE_PATTERN,
                                max_depth=4, max_requests=200)
    import pandas as pd

    pd.DataFrame(tables, columns=["path", "text"]).to_csv(out / "scb_tables.csv", index=False)
    metas = {}
    for t in tables[:25]:
        try:
            metas[t["path"]] = scb.summarise_metadata(get(f"{scb.SCB_BASE}/{t['path']}"))
        except Exception as exc:  # noqa: BLE001
            metas[t["path"]] = {"error": str(exc)[:300]}
    _write_json(out / "scb_table_meta.json", {"n_tables": len(tables), "errors": errors, "tables": metas})
    print(f"SCB: {len(tables)} matching tables, {len(errors)} errors")


def stage_fetch() -> None:
    """M2: download every KPI in config.FETCH_KPIS for config.YEARS (all genders),
    and school-unit SALSA values with the unit register (for reconciliation)."""
    import pandas as pd

    get = kolada.make_getter(timeout=config.HTTP_TIMEOUT, user_agent=config.USER_AGENT)
    base, _ = _detect_base(get)
    frames, per_kpi = [], {}
    for kpi_id in config.FETCH_KPIS:
        df = kolada.parse_data(kolada.paginate(kolada.data_url(base, [kpi_id], config.YEARS), get))
        if df.empty:
            raise SystemExit(f"fetch: no data for {kpi_id}")
        frames.append(df)
        t = df[df["gender"] == "T"]
        per_kpi[kpi_id] = {"rows": int(len(df)),
                           "values_T_per_year": t.groupby("period")["value"].count().astype(int).to_dict()}
    data = pd.concat(frames).sort_values(["kpi", "municipality", "period", "gender"]).reset_index(drop=True)
    kdir = config.RAW / "kolada"
    _write_csv_gz(data, kdir / "kolada_long.csv.gz")

    titles = pd.read_csv(config.PROBE_DIR / "kpi_candidates.csv").set_index("id")["title"].to_dict()
    manifest = {"fetched_utc": datetime.now(timezone.utc).isoformat(), "api": base, "years": config.YEARS,
                "kpis": {k: {"title": titles.get(k), **v} for k, v in per_kpi.items()},
                "n_rows": int(len(data))}

    # School-unit SALSA (Skolverket's model values) -> reconciliation in M5. Not critical.
    try:
        ou = kolada.parse_ou_data(kolada.paginate(kolada.ou_data_url(base, config.SALSA_OU_KPIS, config.YEARS), get))
        munis = pd.read_csv(config.PROBE_DIR / "municipalities.csv", dtype=str)
        from municipalities import is_kommun

        regs = []
        for m in sorted(munis.loc[munis["id"].map(is_kommun), "id"]):
            regs.append(kolada.parse_ou_register(kolada.paginate(kolada.ou_register_url(base, m), get)))
        reg = pd.concat(regs)
        ou = ou[ou["ou"].isin(reg["ou"])].merge(reg[["ou", "municipality"]], on="ou", how="left")
        _write_csv_gz(ou.sort_values(["kpi", "ou", "period", "gender"]), kdir / "salsa_school_units.csv.gz")
        counts = ou[ou["value"].notna()].groupby(["kpi", "period"]).size()
        manifest["salsa_ou"] = {"rows": int(len(ou)), "units": int(ou["ou"].nunique()),
                                "per_kpi_year": {f"{k}_{p}": int(n) for (k, p), n in counts.items()}}
    except Exception as exc:  # noqa: BLE001
        manifest["salsa_ou"] = {"error": f"{type(exc).__name__}: {exc}"[:500]}
    _write_json(kdir / "fetch_manifest.json", manifest)
    print(json.dumps({k: v["values_T_per_year"] for k, v in manifest["kpis"].items()})[:3000])

def stage_reconcile() -> None:
    """M3: SCB table LE0201Utb/Tema42 (national merit value by sex; Skolverket data via SCB)
    for an external check of Kolada's national figures."""
    import scb

    get = kolada.make_getter(timeout=config.HTTP_TIMEOUT, user_agent=config.USER_AGENT)
    url = f"{scb.SCB_BASE}/{config.SCB_RECONCILE_TABLE}"
    meta = get(url)
    import requests

    r = requests.post(url, json=scb.select_all_query(meta), timeout=config.HTTP_TIMEOUT,
                      headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    df = scb.px_to_frame(meta, r.json())
    if df.select_dtypes("number").notna().sum().sum() == 0:
        raise SystemExit("reconcile: SCB returned no numeric values")
    out = config.RAW / "scb"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "tema42_merit_national.csv", index=False)
    _write_json(out / "tema42_meta.json", scb.summarise_metadata(meta))
    print(df.head(12).to_string())


def _load_inputs():
    import pandas as pd

    raw = pd.read_csv(config.RAW / "kolada" / "kolada_long.csv.gz", dtype={"municipality": str, "status": str})
    ou_path = config.RAW / "kolada" / "salsa_school_units.csv.gz"
    ou = pd.read_csv(ou_path, dtype={"municipality": str, "ou": str, "status": str}) if ou_path.exists() else None
    names = pd.read_csv(config.PROBE_DIR / "municipalities.csv", dtype=str)
    return raw, ou, names


def stage_quality() -> None:
    """M3 (offline): analysis panel + data-quality summary and report."""
    import pandas as pd

    import dataset
    import quality

    raw, ou, names = _load_inputs()
    panel = dataset.build_panel(raw, ou, names, config.YEARS)
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    panel.to_csv(config.PROCESSED / "panel.csv", index=False, lineterminator="\n", float_format="%.6g")
    scb_path = config.RAW / "scb" / "tema42_merit_national.csv"
    scb_cmp, scb_error = None, None
    if scb_path.exists():
        try:
            scb_cmp = quality.scb_comparison(pd.read_csv(scb_path), raw)
        except Exception as exc:  # noqa: BLE001 - optional external check; recorded, not hidden
            scb_error = f"{type(exc).__name__}: {exc}"
    summary = quality.summarise(panel, raw, ou, scb_cmp)
    if scb_error:
        summary["scb_error"] = scb_error
    pub_path = ROOT / "data" / "reference" / "skolverket_published_merit.csv"
    if scb_cmp is not None and pub_path.exists():
        ex = quality.scb_vs_published(scb_cmp, raw, pd.read_csv(pub_path))
        d16 = (ex["scb_combined"] - ex["skolverket_16"]).abs().max()
        d17 = (ex["kolada_total"] - ex["skolverket_17"]).abs().max()
        summary["scb_explained"] = {
            "rows": json.loads(ex.to_json(orient="records")),
            "max_abs_diff_16": round(float(d16), 2), "max_abs_diff_17": round(float(d17), 2)}
    _write_json(config.REPORTS / "data_quality_summary.json", summary)
    (ROOT / "docs" / "data_quality.md").write_text(quality.render_markdown(summary), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("panel_rows", "range_violations", "max_abs_reconciliation_diff")}))


def stage_bi() -> None:
    """BI layer (offline): SQLite star schema + SQL views, exported to reports/bi/ for Power BI."""
    import bi

    print(json.dumps(bi.main()))


def stage_descriptives() -> None:
    """M4 (offline): rank stability, churn, cohort-noise model, funnel, figures and a first map."""
    import pandas as pd

    import descriptives
    import figures

    p = pd.read_csv(config.PROCESSED / "panel.csv", dtype={"municipality": str, "county": str})
    s = descriptives.summarise(p, year=config.YEARS[-1], seed=config.SEED)
    _write_json(config.REPORTS / "descriptives.json", s)
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    a, b = s["noise_model"]["point"]["a"], s["noise_model"]["point"]["b"]
    bands = s["change_95_band_by_cohort"]
    figures.changes_vs_size(
        descriptives.demeaned_changes(p), a, b, config.FIGURES / "changes_vs_size.png",
        title=f"With 100 pupils a year, a {bands['100']:.0f}-point swing is within cohort noise; "
              f"with 1,000, {bands['1000']:.0f}")
    figures.funnel_plot(descriptives.funnel(p, "merit", s["funnel_year"], s["noise_model"]["point"]["pupil_sd"]),
                        s["funnel_year"], config.FIGURES / f"funnel_{s['funnel_year']}.png")
    try:
        import geopandas as gpd

        g = gpd.read_file(config.RAW / "geo" / "kommuner.geojson").to_crs(3006)
        y = config.YEARS[-1]
        g = g.merge(p[p["year"] == y][["municipality", "merit"]], left_on="kommun", right_on="municipality",
                    how="left")
        if g["merit"].isna().any():
            raise SystemExit(f"map: {int(g['merit'].isna().sum())} municipalities without a value")
        figures.choropleth(g, "merit", config.FIGURES / f"map_merit_{y}.png",
                           title=f"Raw merit value {y} by municipality, before adjusting for pupil background",
                           label=f"Average merit value, grade 9, {y} (points)")
    except ImportError:
        print("geopandas not installed: map skipped")
    print(json.dumps({k: s[k] for k in ("rank_stability_mean", "top_decile_stay_mean", "bottom_decile_stay_mean",
                                        "share_changes_inside_band", "funnel_outside95")}))


def _panel():
    import pandas as pd

    return pd.read_csv(config.PROCESSED / "panel.csv", dtype={"municipality": str, "county": str})


def stage_expected() -> None:
    """M5: expected merit value from pupil background (D8, D11) + SALSA reconciliation."""
    import analysis
    import figures

    out, d, f = analysis.expected_value(_panel())
    _write_json(config.REPORTS / "expected_value.json", out)
    d[["municipality", "name", "year", "merit", "expected", "resid", "cohort_est"]].to_csv(
        config.PROCESSED / "expected_values.csv", index=False, lineterminator="\n", float_format="%.4f")
    y = config.YEARS[-1]
    figures.actual_vs_expected(
        d, y, config.FIGURES / f"actual_vs_expected_{y}.png",
        title=f"Pupil background explains {out['within_year_r2_chosen']:.0%} of the differences "
              f"between municipalities")
    print(json.dumps({k: out[k] for k in ("r2_chosen", "within_year_r2_chosen", "reset_p_linear",
                                          "d11_use_quadratic", "breusch_pagan_p")}))
    print(json.dumps(out.get("salsa")))


def _stockholm_title(eff) -> str:
    s = eff[eff["county"] == config.STOCKHOLM_COUNTY]
    n_above = int((s["verdict"] == "above").sum())
    return f"Stockholm county: {n_above} of {len(s)} municipalities sit persistently above expected"


def stage_persistence() -> None:
    """M6: persistent municipality effect vs year-to-year noise, rank intervals, decision rule."""
    import analysis
    import figures
    import models

    p = _panel()
    exp = json.loads((config.REPORTS / "expected_value.json").read_text(encoding="utf-8"))
    f = exp["formula_chosen"]
    d = models.model_frame(p, "merit", ["parents_post_secondary", "foreign_background"])
    out, eff = analysis.persistence(d, f, seed=config.SEED)
    _write_json(config.REPORTS / "persistence.json", out)
    eff.to_csv(config.REPORTS / "municipality_effects.csv", index=False, lineterminator="\n", float_format="%.4f")
    sd = out["size_dependent"]
    figures.caterpillar(eff, config.FIGURES / "persistent_effects.png",
                        title=f"After background, {sd['verdicts'].get('above', 0) + sd['verdicts'].get('below', 0)} "
                              f"of 290 municipalities differ persistently from expected")
    figures.rank_ranges(eff, config.FIGURES / "rank_intervals_stockholm.png",
                        title=_stockholm_title(eff))
    try:
        import geopandas as gpd

        g = gpd.read_file(config.RAW / "geo" / "kommuner.geojson").to_crs(3006)
        g = g.merge(eff[["municipality", "eb_mean"]], left_on="kommun", right_on="municipality", how="left")
        lim = float(eff["eb_mean"].abs().quantile(0.98))
        figures.choropleth(g, "eb_mean", config.FIGURES / "map_persistent_effects.png",
                           title="Persistent difference from expected merit value, 2015–2025",
                           label="Points above (blue) or below (red) what pupil background predicts",
                           diverging=True, vlim=lim)
    except ImportError:
        print("geopandas not installed: map skipped")
    print(json.dumps({k: out[k] for k in ("homoskedastic", "size_dependent")}, default=str)[:3000])


def stage_robustness() -> None:
    """M7: robustness variants, Stockholm-county table and Moran's I."""
    import pandas as pd

    import figures
    import robustness

    p = _panel()
    exp = json.loads((config.REPORTS / "expected_value.json").read_text(encoding="utf-8"))
    out, wide = robustness.run(p, exp["formula_chosen"], stockholm=config.STOCKHOLM_COUNTY)
    wide.to_csv(config.REPORTS / "robustness_effects.csv", index=False, lineterminator="\n", float_format="%.4f")

    eff = pd.read_csv(config.REPORTS / "municipality_effects.csv", dtype={"municipality": str, "county": str})
    st = eff[eff["county"] == config.STOCKHOLM_COUNTY].merge(
        wide[["municipality", "home municipality", "SALSA expected value as covariate", "municipal schools only"]],
        on="municipality", how="left")
    cols = ["name", "cohort_median", "eb_mean", "lo95", "hi95", "rank_point", "rank_lo", "rank_hi", "verdict",
            "home municipality", "municipal schools only", "SALSA expected value as covariate"]
    st[cols].sort_values("eb_mean", ascending=False).to_csv(
        config.REPORTS / "stockholm_county.csv", index=False, lineterminator="\n", float_format="%.2f")

    try:
        import geopandas as gpd

        g = gpd.read_file(config.RAW / "geo" / "kommuner.geojson").to_crs(3006).sort_values("kommun")
        g = g.merge(eff[["municipality", "eb_mean"]], left_on="kommun", right_on="municipality", how="left")
        g = g.merge(wide[["municipality", "SALSA expected value as covariate"]].rename(
            columns={"SALSA expected value as covariate": "eb_salsa"}), on="municipality", how="left")
        last = p[p["year"] == p["year"].max()][["municipality", "merit"]]
        g = g.merge(last, on="municipality", how="left")
        out["morans_i"] = {
            "persistent_effect_primary": robustness.morans_i(g, "eb_mean", seed=config.SEED),
            "raw_merit_last_year": robustness.morans_i(g, "merit", seed=config.SEED),
        }
        # SALSA variant: 3 municipalities have no SALSA school units and are left out of this one check.
        gs = g.dropna(subset=["eb_salsa"])
        out["morans_i"]["persistent_effect_salsa_covariate"] = robustness.morans_i(gs, "eb_salsa", seed=config.SEED)
    except ImportError:
        print("geopandas/esda not installed: spatial check skipped")
    _write_json(config.REPORTS / "robustness.json", out)
    prim = next(r for r in out["variants"] if r["variant"] == "primary")
    figures.robustness_bars(out["variants"], config.FIGURES / "robustness.png",
                            title=f"Municipalities clearly below / above expected under {len(out['variants'])} "
                                  f"specifications (primary: {prim['below']} / {prim['above']})")
    print(json.dumps(out, default=str)[:4000])


STAGES = {"probe": stage_probe, "probe_scb": stage_probe_scb, "fetch": stage_fetch,
          "reconcile": stage_reconcile, "quality": stage_quality, "descriptives": stage_descriptives,
          "expected": stage_expected, "persistence": stage_persistence, "robustness": stage_robustness,
          "bi": stage_bi}


def main(argv: list[str]) -> None:
    stages = [a for a in argv if a.strip()]
    if not stages:
        raise SystemExit(f"usage: run_pipeline.py <stage> ...; stages: {', '.join(STAGES)}")
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        raise SystemExit(f"unknown stage(s): {unknown}")
    for s in stages:
        print(f"== {s}", flush=True)
        STAGES[s]()


if __name__ == "__main__":
    main(sys.argv[1:])
