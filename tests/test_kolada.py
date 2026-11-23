import math

import pandas as pd
import pytest

import kolada

V2_DATA_PAGE_1 = {
    "count": 3,
    "values": [
        {"kpi": "N15507", "municipality": "0180", "period": 2024,
         "values": [{"count": 1, "gender": "T", "status": "", "value": 241.3},
                    {"count": 1, "gender": "K", "status": "", "value": 252.0}]},
        {"kpi": "N15507", "municipality": "0000", "period": 2024,
         "values": [{"count": 1, "gender": "T", "status": "", "value": 229.8}]},
    ],
    "next_page": "https://api.kolada.se/v2/data/kpi/N15507/year/2024?page=2",
}
V2_DATA_PAGE_2 = {
    "count": 3,
    "values": [
        {"kpi": "N15507", "municipality": "2584", "period": 2024,
         "values": [{"count": 0, "gender": "T", "status": "Missing", "value": None}]},
        {"kpi": "N15507", "municipality": "0001", "period": 2024,
         "values": [{"count": 1, "gender": "T", "status": "", "value": 238.0}]},
    ],
}


def fake_getter(pages):
    calls = []

    def get(url):
        calls.append(url)
        return pages[url]

    get.calls = calls
    return get


def test_paginate_follows_next_page_links():
    first = "https://api.kolada.se/v2/data/kpi/N15507/year/2024"
    get = fake_getter({first: V2_DATA_PAGE_1, V2_DATA_PAGE_1["next_page"]: V2_DATA_PAGE_2})
    pages = list(kolada.paginate(first, get))
    assert len(pages) == 2
    assert get.calls == [first, V2_DATA_PAGE_1["next_page"]]


def test_paginate_accepts_v3_next_url_key():
    first = "https://api.kolada.se/v3/kpi?title=x"
    p1 = {"values": [{"id": "A", "title": "a"}], "next_url": "https://api.kolada.se/v3/kpi?title=x&page=2"}
    p2 = {"values": [{"id": "B", "title": "b"}], "next_url": None}
    get = fake_getter({first: p1, p1["next_url"]: p2})
    assert [v["id"] for p in kolada.paginate(first, get) for v in p["values"]] == ["A", "B"]


def test_paginate_detects_loops_and_missing_values():
    url = "https://api.kolada.se/v2/x"
    loop = {"values": [], "next_page": url}
    with pytest.raises(RuntimeError, match="loop"):
        list(kolada.paginate(url, fake_getter({url: loop})))
    with pytest.raises(kolada.KoladaSchemaError):
        list(kolada.paginate(url, fake_getter({url: {"error": "x"}})))


def test_parse_data_flattens_and_keeps_missing_values():
    df = kolada.parse_data([V2_DATA_PAGE_1, V2_DATA_PAGE_2])
    assert list(df.columns) == kolada.DATA_COLUMNS
    assert len(df) == 5
    missing = df[df["municipality"] == "2584"].iloc[0]
    assert math.isnan(missing["value"]) and missing["status"] == "Missing"
    assert df["period"].dtype.kind == "i"


def test_parse_data_zero_pads_numeric_municipality_ids():
    page = {"values": [{"kpi": "X", "municipality": 180, "period": "2024",
                        "values": [{"gender": "T", "value": "1.5"}]}]}
    df = kolada.parse_data([page])
    assert df.loc[0, "municipality"] == "0180" and df.loc[0, "value"] == 1.5


def test_parse_data_fails_loudly_on_schema_change():
    with pytest.raises(kolada.KoladaSchemaError, match="municipality"):
        kolada.parse_data([{"values": [{"kpi": "X", "period": 2024, "values": []}]}])
    with pytest.raises(kolada.KoladaSchemaError, match="gender"):
        kolada.parse_data([{"values": [{"kpi": "X", "municipality": "0180", "period": 2024,
                                        "values": [{"value": 1}]}]}])


def test_coverage_counts_only_kommuner_and_total_gender():
    df = kolada.parse_data([V2_DATA_PAGE_1, V2_DATA_PAGE_2])
    cov = kolada.coverage(df)
    row = cov.iloc[0]
    # 0180 and 2584 are municipalities; 0000 (Riket) and 0001 (a region) are not.
    assert row["n_rows"] == 2 and row["n_values"] == 1
    assert row["mean"] == pytest.approx(241.3)
    assert row["statuses"] == "Missing"


def test_parse_kpis_dedupes_and_requires_id_title():
    p = {"values": [{"id": "N1", "title": "Elever i åk 9, meritvärde", "municipality_type": "K"},
                    {"id": "N1", "title": "Elever i åk 9, meritvärde", "municipality_type": "K"}]}
    assert len(kolada.parse_kpis([p])) == 1
    with pytest.raises(kolada.KoladaSchemaError):
        kolada.parse_kpis([{"values": [{"title": "no id"}]}])


def test_grade9_candidates_filters_on_title_and_level():
    kpis = pd.DataFrame([
        {"id": "N15507", "title": "Elever i åk 9: Genomsnittligt meritvärde, hemkommun", "municipality_type": "K"},
        {"id": "U15001", "title": "Elever i årskurs 9, meritvärde, skolenhet", "municipality_type": "L"},
        {"id": "N15999", "title": "Elever i ÅK 9 behöriga till yrkesprogram", "municipality_type": "A"},
        {"id": "N00001", "title": "Invånare 0-19 år", "municipality_type": "K"},
        {"id": "N15998", "title": "Elever i åk 6, betyg", "municipality_type": "K"},
    ])
    got = kolada.grade9_candidates(kpis, ["åk 9", "årskurs 9"])
    assert list(got["id"]) == ["N15507", "N15999"]


def test_urls_are_encoded():
    assert kolada.kpi_search_url("https://api.kolada.se/v2", "meritvärde åk 9") == \
        "https://api.kolada.se/v2/kpi?title=meritv%C3%A4rde%20%C3%A5k%209"
    assert kolada.data_url("https://api.kolada.se/v2", ["N1", "N2"], [2015, 2024]) == \
        "https://api.kolada.se/v2/data/kpi/N1,N2/year/2015,2024"


def test_parse_ou_data_and_register():
    page = {"values": [{"kpi": "U15416", "ou": "V15E018000101", "period": 2024,
                        "values": [{"gender": "T", "value": 4.2, "status": ""}]},
                       {"kpi": "U15416", "ou": "V15E018000102", "period": 2024,
                        "values": [{"gender": "T", "value": None, "status": "Missing"}]}]}
    df = kolada.parse_ou_data([page])
    assert len(df) == 2 and df["value"].isna().sum() == 1
    reg = kolada.parse_ou_register([{"values": [{"id": "V15E018000101", "municipality": 180, "title": "Skola A"}]}])
    assert reg.loc[0, "municipality"] == "0180"
    with pytest.raises(kolada.KoladaSchemaError):
        kolada.parse_ou_data([{"values": [{"kpi": "U1", "period": 2024, "values": []}]}])
    assert kolada.ou_data_url("https://api.kolada.se/v3", ["U1"], [2024]) == \
        "https://api.kolada.se/v3/oudata/kpi/U1/year/2024"
