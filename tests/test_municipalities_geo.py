import pytest

from geo import find_download_links, rank_deso_links
from municipalities import county_of, is_kommun, kommun_from_deso


@pytest.mark.parametrize("code", ["0114", "0180", "0980", "1480", "2584", "0360"])
def test_real_kommun_codes(code):
    assert is_kommun(code)


@pytest.mark.parametrize("code", ["0000", "0001", "0025", "180", "01800", "1180", "2600", "ab12", None])
def test_not_kommun_codes(code):
    # 11xx, 15xx, 16xx: counties merged into Skåne/Västra Götaland in 1997-98.
    assert not is_kommun(code)


def test_county_and_deso():
    assert county_of("0180") == "01"
    assert county_of(180) == "01"
    assert kommun_from_deso("0114A0010") == "0114"
    assert kommun_from_deso("2584C1030") == "2584"
    with pytest.raises(ValueError):
        kommun_from_deso("0001A0010")
    with pytest.raises(ValueError):
        county_of("0001")


HTML = """
<html><body>
<a href="/contentassets/abc/deso_2018_v2.zip">DeSO 2018 (shape)</a>
<a href="https://www.scb.se/contentassets/def/DeSO_2025.gpkg?v=3">DeSO 2025 (GeoPackage)</a>
<a href="/contentassets/def/DeSO_2025.gpkg?v=3">duplicate relative</a>
<a href="/hitta-statistik/">not a file</a>
<a>no href</a>
</body></html>
"""


def test_find_download_links_handles_absolute_and_relative():
    base = "https://www.scb.se/vara-tjanster/oppna-data/oppna-geodata/deso/"
    links = find_download_links(HTML, base)
    assert links == [
        "https://www.scb.se/contentassets/abc/deso_2018_v2.zip",
        "https://www.scb.se/contentassets/def/DeSO_2025.gpkg?v=3",
    ]


def test_rank_prefers_recent_geopackage():
    links = [
        "https://x/deso_2018_v2.zip",
        "https://x/DeSO_2025.gpkg?v=3",
        "https://x/DeSO_2018.gpkg",
    ]
    assert rank_deso_links(links)[0] == "https://x/DeSO_2025.gpkg?v=3"
    assert rank_deso_links(links)[-1] == "https://x/deso_2018_v2.zip"


CAPS_WFS2 = """<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" version="2.0.0">
  <FeatureTypeList>
    <FeatureType><Name>stat:DeSO_2018</Name><Title>DeSO 2018</Title></FeatureType>
    <FeatureType><Name>stat:DeSO_2025</Name><Title>DeSO 2025</Title></FeatureType>
    <FeatureType><Name>stat:RegSO_DeSO_2025</Name></FeatureType>
    <FeatureType><Name>stat:Tatorter_2023</Name></FeatureType>
  </FeatureTypeList>
</wfs:WFS_Capabilities>"""


def test_wfs_feature_types_and_deso_pick():
    from geo import pick_deso_layer, wfs_feature_types, wfs_getfeature_url

    names = wfs_feature_types(CAPS_WFS2)
    assert names == ["stat:DeSO_2018", "stat:DeSO_2025", "stat:RegSO_DeSO_2025", "stat:Tatorter_2023"]
    assert pick_deso_layer(names) == "stat:DeSO_2025"
    assert pick_deso_layer(["stat:Tatorter_2023"]) is None
    url = wfs_getfeature_url("https://geodata.scb.se/geoserver/stat/wfs", "stat:DeSO_2025")
    assert "typeNames=stat%3ADeSO_2025" in url and "outputFormat=application%2Fjson" in url
