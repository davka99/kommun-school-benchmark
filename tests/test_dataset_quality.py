import numpy as np
import pandas as pd
import pytest

import dataset
import quality

YEARS = [2023, 2024]
MUNIS = ["0114", "0180", "2584"]


def raw_fixture():
    rows = []
    rng = np.random.default_rng(0)
    for m in MUNIS + ["0000", "0001", "G12345"]:
        for y in YEARS:
            for name, kpi in dataset.VARIABLES.items():
                v = 1000.0 if name == "pupils_1_9" else (220.0 if name.startswith("merit") else 50.0)
                v += rng.integers(0, 10)
                rows.append({"kpi": kpi, "municipality": m, "period": y, "gender": "T", "value": v,
                             "count": 1, "status": ""})
                rows.append({"kpi": kpi, "municipality": m, "period": y, "gender": "K", "value": v + 5,
                             "count": 1, "status": ""})
    return pd.DataFrame(rows)


NAMES = pd.DataFrame({"id": MUNIS + ["0001"], "title": ["Upplands Väsby", "Stockholm", "Kiruna", "Region"],
                      "type": ["K", "K", "K", "L"]})


def test_kommun_rows_drops_country_regions_and_groups():
    k = dataset.kommun_rows(raw_fixture())
    assert set(k["municipality"]) == set(MUNIS) and set(k["gender"]) == {"T"}


def test_build_panel_shape_names_and_county():
    p = dataset.build_panel(raw_fixture(), None, NAMES, YEARS)
    assert len(p) == 6 and list(p.columns[:3]) == ["municipality", "name", "year"]
    assert p.loc[p["municipality"] == "0180", "name"].iloc[0] == "Stockholm"
    assert p.loc[p["municipality"] == "2584", "county"].iloc[0] == "25"
    assert p["stockholm_county"].sum() == 4
    assert p["cohort_est"].iloc[0] == pytest.approx(p["pupils_1_9"].iloc[0] / 9)


def test_build_panel_rejects_missing_municipality_year():
    raw = raw_fixture()
    raw = raw[~((raw["municipality"] == "2584") & (raw["period"] == 2024))]
    with pytest.raises(ValueError, match="expected 6"):
        dataset.build_panel(raw, None, NAMES, YEARS)


def test_wide_panel_rejects_duplicates():
    raw = raw_fixture()
    raw = pd.concat([raw, raw.iloc[[0]]])
    with pytest.raises(ValueError, match="duplicated"):
        dataset.wide_panel(raw, YEARS)


def test_salsa_aggregation_is_unweighted_mean_per_municipality():
    ou = pd.DataFrame([
        {"kpi": "U15415", "ou": "A", "period": 2024, "gender": "T", "value": 200.0, "municipality": "0180"},
        {"kpi": "U15415", "ou": "B", "period": 2024, "gender": "T", "value": 240.0, "municipality": "0180"},
        {"kpi": "U15416", "ou": "A", "period": 2024, "gender": "T", "value": 10.0, "municipality": "0180"},
        {"kpi": "U15416", "ou": "B", "period": 2024, "gender": "T", "value": -4.0, "municipality": "0180"},
        {"kpi": "U15415", "ou": "C", "period": 2024, "gender": "T", "value": np.nan, "municipality": "0114"},
    ])
    s = dataset.salsa_by_municipality(ou)
    row = s[s["municipality"] == "0180"].iloc[0]
    assert row["salsa_expected"] == 220.0 and row["salsa_deviation"] == 3.0 and row["salsa_units"] == 2
    assert "0114" not in set(s["municipality"])  # only missing values -> no row


def test_weighted_national_uses_pupil_weights():
    p = pd.DataFrame({"year": [2024, 2024], "merit": [200.0, 230.0], "pupils_1_9": [100, 200]})
    assert dataset.weighted_national(p, "merit")[2024] == pytest.approx(220.0)


def test_year_to_year_changes_require_consecutive_years():
    p = pd.DataFrame({"municipality": ["0180"] * 3, "name": ["S"] * 3, "year": [2019, 2020, 2022],
                      "merit": [220.0, 230.0, 225.0], "cohort_est": [900.0] * 3})
    ch = quality.year_to_year_changes(p)
    assert list(ch["change"]) == [10.0]


def test_size_bands_and_range_violations():
    b = quality.size_bands(pd.Series([10, 50, 99.9, 150, 600]))
    assert list(b.astype(str)) == ["<50", "50-99", "50-99", "100-199", "500+"]
    p = dataset.build_panel(raw_fixture(), None, NAMES, YEARS)
    p.loc[0, "parents_post_secondary"] = 101
    p.loc[1, "merit"] = 341
    v = quality.range_violations(p)
    assert v["parents_post_secondary"] == 1 and v["merit"] == 1 and v["foreign_background"] == 0


def test_national_reconciliation_against_country_row():
    raw = raw_fixture()
    p = dataset.build_panel(raw, None, NAMES, YEARS)
    rec = quality.national_reconciliation(p, raw, ["merit"])
    assert len(rec) == 2 and rec["kolada_national"].notna().all()
    assert (rec["difference"] == (rec["weighted_mean"] - rec["kolada_national"]).round(2)).all()


def test_scb_comparison_filters_totals_and_maps_sex():
    tema = pd.DataFrame([
        {"SvUtlBakgrund": "totalt", "ForUtb": "totalt", "Kon": "flickor", "Tid": "2023/24", "V": 240.0},
        {"SvUtlBakgrund": "totalt", "ForUtb": "totalt", "Kon": "pojkar", "Tid": "2023/24", "V": 215.0},
        {"SvUtlBakgrund": "svensk bakgrund", "ForUtb": "totalt", "Kon": "pojkar", "Tid": "2023/24", "V": 1.0},
    ])
    raw = pd.DataFrame([
        {"kpi": "N15504", "municipality": "0000", "period": 2024, "gender": "K", "value": 240.5},
        {"kpi": "N15504", "municipality": "0000", "period": 2024, "gender": "M", "value": 215.0},
        {"kpi": "N15504", "municipality": "0180", "period": 2024, "gender": "M", "value": 1.0},
    ])
    m = quality.scb_comparison(tema, raw)
    assert list(m["sex"]) == ["K", "M"] and list(m["difference"]) == [0.5, 0.0]
