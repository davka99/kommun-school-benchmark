"""The SQL layer (sql/, src/bi.py) must reproduce the Python results it is built from."""

import json

import pandas as pd
import pytest

import bi
import config


@pytest.fixture(scope="module")
def con():
    needed = [config.PROCESSED / "panel.csv", config.REPORTS / "municipality_effects.csv"]
    if not all(p.exists() for p in needed):
        pytest.skip("results not generated yet")
    c = bi.connect()
    bi.build(c, bi.load_frames())
    yield c
    c.close()


def test_verdict_counts_match_python(con):
    sql = bi.query(con, "SELECT * FROM v_verdict_counts").set_index("verdict")["n_municipalities"]
    eff = pd.read_csv(config.REPORTS / "municipality_effects.csv")
    assert sql.to_dict() == eff["verdict"].value_counts().to_dict()


def test_stockholm_county_summary(con):
    row = bi.query(con, "SELECT * FROM v_county_summary WHERE county = '01'").iloc[0]
    assert row["n_municipalities"] == 26
    sc = pd.read_csv(config.REPORTS / "stockholm_county.csv")
    assert row["n_above"] == (sc["verdict"] == "above").sum()


def test_noise_band_view_reproduces_descriptives(con):
    v = bi.query(con, "SELECT * FROM v_change_vs_noise")
    desc = json.loads((config.REPORTS / "descriptives.json").read_text(encoding="utf-8"))
    assert round(1 - v["outside_band"].mean(), 3) == desc["share_changes_inside_band"]


def test_municipality_card_three_year_average(con):
    card = bi.query(con, "SELECT municipality, resid_3y_avg FROM v_municipality_card")
    ev = pd.read_csv(config.PROCESSED / "expected_values.csv", dtype={"municipality": str})
    last = ev["year"].max()
    py = ev[ev["year"] > last - 3].groupby("municipality")["resid"].mean().round(1)
    merged = card.set_index("municipality")["resid_3y_avg"]
    assert len(merged) == 290
    assert (merged - py.reindex(merged.index)).abs().max() <= 0.051


def test_change_view_on_synthetic_data():
    """synthetic: two municipalities, three years; known changes and bands."""
    c = bi.connect()
    frames = {
        "dim_municipality": pd.DataFrame({"municipality": ["A", "B"], "name": ["a", "b"],
                                          "county": ["01", "02"], "stockholm_county": [1, 0],
                                          "cohort_median": [100.0, 100.0]}),
        "dim_year": pd.DataFrame({"year": [2023, 2024, 2025]}),
        "fact_results": pd.DataFrame({
            "municipality": ["A"] * 3 + ["B"] * 3, "year": [2023, 2024, 2025] * 2,
            "merit": [200.0, 210.0, 210.0, 200.0, 200.0, 240.0],
            "expected": 200.0, "resid": 0.0, "cohort_est": 100.0,
            "parents_post_secondary": 50.0, "foreign_background": 20.0}),
        "fact_effects": pd.DataFrame({"municipality": ["A", "B"], "eb_mean": [1.0, -1.0],
                                      "lo95": 0.0, "hi95": 2.0,
                                      "verdict": ["above", "not distinguishable"],
                                      "rank_point": [1, 2], "rank_lo": 1, "rank_hi": 2,
                                      "p_top_decile": 0.5, "p_bottom_decile": 0.5}),
        "param_noise": pd.DataFrame([{"a": 0.0, "b": 10000.0}]),  # band = 1.96 * 10 = 19.6
    }
    bi.build(c, frames)
    v = bi.query(c, "SELECT * FROM v_change_vs_noise ORDER BY municipality, year")
    assert v["noise_band_95"].tolist() == [19.6] * 4
    # 2024: changes +10 and 0, mean 5 -> demeaned +5 / -5; 2025: 0 and +40, mean 20 -> -20 / +20
    assert v["change_vs_national"].tolist() == [5.0, -20.0, -5.0, 20.0]
    assert v["outside_band"].tolist() == [0, 1, 0, 1]
    c.close()
