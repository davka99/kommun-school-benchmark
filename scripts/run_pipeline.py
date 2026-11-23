"""Pipeline entry point. Usage: python scripts/run_pipeline.py <stage> [<stage> ...]

Stages
  probe  Verify the sources before any full fetch (M1). Detects the Kolada API
         version, lists candidate KPIs for the search terms in config.py, checks
         municipality coverage of every grade-9 candidate for config.PROBE_YEAR,
         lists the municipality register, and finds, downloads and dissolves SCB's
         DeSO layer to municipalities. Writes data/raw/_probe/ and, if the geodata
         works, data/raw/geo/kommuner.geojson. Every check is recorded in
         data/raw/_probe/probe_report.json; the stage fails if a critical check fails.

Network access is only needed for `probe` (and the later `fetch`). The build
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


STAGES = {"probe": stage_probe}


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
