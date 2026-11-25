"""BI layer: load the analysis results into a SQLite star schema, run the SQL views in
sql/ and export Power BI-ready tables to reports/bi/ (see docs/powerbi.md).

    python scripts/run_pipeline.py bi

The SQL is plain SQLite; sqrt() is registered from Python so it runs on any build.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pandas as pd

import config

ROOT = config.PROCESSED.parents[1]
SQL_DIR = ROOT / "sql"
OUT_DIR = config.REPORTS / "bi"
EXPORTS = ["dim_municipality", "dim_year", "fact_results", "fact_effects",
           "v_verdict_counts", "v_county_summary", "v_change_vs_noise", "v_municipality_card"]


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.create_function("sqrt", 1, lambda x: None if x is None or x < 0 else math.sqrt(x),
                        deterministic=True)
    return con


def _read(name: str, folder: Path) -> pd.DataFrame:
    return pd.read_csv(folder / name, dtype={"municipality": str, "county": str})


def load_frames(processed: Path = config.PROCESSED, reports: Path = config.REPORTS) -> dict:
    panel = _read("panel.csv", processed)
    expected = _read("expected_values.csv", processed)
    effects = _read("municipality_effects.csv", reports)
    noise = json.loads((reports / "descriptives.json").read_text(encoding="utf-8"))["noise_model"]

    dim_m = (panel.groupby("municipality")
             .agg(name=("name", "first"), county=("county", "first"),
                  stockholm_county=("stockholm_county", "first"))
             .reset_index()
             .merge(effects[["municipality", "cohort_median"]], on="municipality", how="left"))
    dim_m["stockholm_county"] = dim_m["stockholm_county"].astype(bool).astype(int)
    fact = panel[["municipality", "year", "merit", "cohort_est", "parents_post_secondary",
                  "foreign_background"]].merge(
        expected[["municipality", "year", "expected", "resid"]],
        on=["municipality", "year"], how="left", validate="one_to_one")
    fact = fact[["municipality", "year", "merit", "expected", "resid", "cohort_est",
                 "parents_post_secondary", "foreign_background"]]
    eff = effects[["municipality", "eb_mean", "lo95", "hi95", "verdict", "rank_point",
                   "rank_lo", "rank_hi", "p_top_decile", "p_bottom_decile"]]
    return {
        "dim_municipality": dim_m,
        "dim_year": pd.DataFrame({"year": sorted(panel["year"].unique())}),
        "fact_results": fact,
        "fact_effects": eff,
        "param_noise": pd.DataFrame([{"a": noise["point"]["a"], "b": noise["point"]["b"]}]),
    }


def build(con: sqlite3.Connection, frames: dict) -> None:
    con.executescript((SQL_DIR / "01_schema.sql").read_text(encoding="utf-8"))
    for table, df in frames.items():
        cols = ", ".join(df.columns)
        marks = ", ".join("?" for _ in df.columns)
        rows = [tuple(None if pd.isna(v) else v for v in r) for r in df.itertuples(index=False)]
        con.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", rows)
    con.executescript((SQL_DIR / "02_views.sql").read_text(encoding="utf-8"))
    con.commit()


def query(con: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, con)


def main() -> dict:
    con = connect()
    build(con, load_frames())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name in EXPORTS:
        df = query(con, f"SELECT * FROM {name}")
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, lineterminator="\n")
        sizes[name] = len(df)
    con.close()
    return sizes
