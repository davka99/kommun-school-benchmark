import pytest

import scb


def test_parse_node_list():
    nodes = scb.parse_node_list([{"id": "UF", "type": "l", "text": "Utbildning"},
                                 {"id": "T1", "type": "t", "text": "Elever i årskurs 9", "updated": "x"}])
    assert nodes[1] == {"id": "T1", "type": "t", "text": "Elever i årskurs 9"}
    with pytest.raises(ValueError):
        scb.parse_node_list({"title": "a table"})
    with pytest.raises(ValueError):
        scb.parse_node_list([{"text": "no id"}])


def test_browse_finds_matching_tables_and_limits_depth():
    tree = {
        "UF": [{"id": "UF01", "type": "l", "text": "Skolväsende"}],
        "UF/UF01": [{"id": "A", "type": "l", "text": "Grundskolan"},
                    {"id": "T0", "type": "t", "text": "Meritvärde årskurs 9 efter kommun"}],
        "UF/UF01/A": [{"id": "T1", "type": "t", "text": "Elever i årskurs 9 efter föräldrarnas utbildning"},
                      {"id": "T2", "type": "t", "text": "Lärare"},
                      {"id": "B", "type": "l", "text": "Övrigt"}],
        "UF/UF01/A/B": [{"id": "T3", "type": "t", "text": "Årskurs 9 deep"}],
    }

    def get(url):
        path = url.split("/ssd/")[1]
        if path not in tree:
            raise RuntimeError("404")
        return tree[path]

    tables, errors = scb.browse(get, ["UF"], r"årskurs 9", max_depth=3, pause=0)
    paths = [t["path"] for t in tables]
    assert paths == ["UF/UF01/T0", "UF/UF01/A/T1"]  # 'Övrigt' does not match and is at depth 3
    assert errors == []


def test_summarise_metadata():
    meta = {"title": "t", "variables": [
        {"code": "Region", "text": "region", "values": ["0114", "0115"], "valueTexts": ["Upplands Väsby", "Vallentuna"]},
        {"code": "Tid", "text": "år", "values": ["2024"], "valueTexts": ["2024"], "time": True}]}
    s = scb.summarise_metadata(meta)
    assert s["variables"][0]["n_values"] == 2 and s["variables"][1]["time"] is True
    assert s["variables"][1]["last"] == "2024"


def test_px_to_frame_maps_codes_to_texts():
    meta = {"variables": [
        {"code": "Kon", "values": ["1", "2"], "valueTexts": ["flickor", "pojkar"]},
        {"code": "Tid", "values": ["2014/15"], "valueTexts": ["2014/15"]}]}
    result = {"columns": [{"code": "Kon", "type": "d"}, {"code": "Tid", "type": "t"},
                          {"code": "X", "type": "c"}],
              "data": [{"key": ["1", "2014/15"], "values": ["240.1"]},
                       {"key": ["2", "2014/15"], "values": [".."]}]}
    df = scb.px_to_frame(meta, result)
    assert list(df["Kon"]) == ["flickor", "pojkar"]
    assert df.loc[0, "X"] == 240.1 and df["X"].isna().iloc[1]
    assert scb.school_year_to_spring("2014/15") == 2015


def test_select_all_query_lists_every_variable():
    meta = {"variables": [{"code": "SvUtlBakgrund"}, {"code": "Kon"}, {"code": "Tid"}]}
    q = scb.select_all_query(meta)
    assert [x["code"] for x in q["query"]] == ["SvUtlBakgrund", "Kon", "Tid"]
    assert all(x["selection"] == {"filter": "all", "values": ["*"]} for x in q["query"])
