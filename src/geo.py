"""Geodata helpers. Link discovery is pure Python; geometry work needs geopandas
(installed in GitHub Actions) and is imported lazily."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def find_download_links(html: str, base_url: str, exts=(".gpkg", ".zip", ".geojson")) -> list[str]:
    """Absolute URLs of links whose path ends with one of `exts` (query strings ignored).

    Handles absolute and relative hrefs; keeps page order; no duplicates.
    """
    p = _Links()
    p.feed(html)
    out = []
    for href, _ in p.links:
        if not href:
            continue
        path = re.split(r"[?#]", href)[0].lower()
        if path.endswith(tuple(e.lower() for e in exts)):
            url = urljoin(base_url, href)
            if url not in out:
                out.append(url)
    return out


def rank_deso_links(urls: list[str]) -> list[str]:
    """Prefer GeoPackage over zip and the most recent year mentioned in the file name."""

    def key(u):
        name = u.rsplit("/", 1)[-1].lower()
        years = [int(y) for y in re.findall(r"20\d{2}", name)]
        return (
            0 if name.endswith(".gpkg") or ".gpkg" in name else 1,
            0 if "deso" in name else 1,
            -(max(years) if years else 0),
        )

    return sorted(urls, key=key)


def wfs_feature_types(capabilities_xml: str) -> list[str]:
    """Feature type names from a WFS GetCapabilities document (any WFS version)."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(capabilities_xml)
    names = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "FeatureType":
            for child in el:
                if child.tag.split("}")[-1] == "Name" and child.text:
                    names.append(child.text.strip())
    return names


def pick_deso_layer(names: list[str]) -> str | None:
    """The most recent DeSO layer (e.g. 'stat:DeSO_2025'); None if there is none."""
    cands = [n for n in names if re.search(r"deso", n, re.I) and not re.search(r"regso", n, re.I)]
    if not cands:
        return None

    def year(n):
        ys = [int(y) for y in re.findall(r"20\d{2}", n)]
        return max(ys) if ys else 0

    return sorted(cands, key=lambda n: (-year(n), n))[0]


def wfs_getfeature_url(base: str, layer: str, srs: str = "EPSG:3006") -> str:
    from urllib.parse import urlencode

    q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
         "outputFormat": "application/json", "srsName": srs}
    return f"{base}?{urlencode(q)}"


def dissolve_to_kommun(gdf, code_col: str):
    """Dissolve DeSO polygons to municipalities (geopandas GeoDataFrame in, out)."""
    from municipalities import kommun_from_deso

    g = gdf[[code_col, "geometry"]].copy()
    g["kommun"] = g[code_col].map(kommun_from_deso)
    out = g.dissolve(by="kommun", as_index=False)[["kommun", "geometry"]]
    return out.sort_values("kommun").reset_index(drop=True)
