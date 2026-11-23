"""Project configuration. Everything that changes a result lives here or in docs/decisions.md."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROBE_DIR = RAW / "_probe"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
TMP = DATA / "tmp"

SEED = 20261123

# Kolada (Rådet för främjande av kommunala analyser, RKA). Open REST API, no key.
# v3 is tried first; v2 is the documented fallback (D5).
KOLADA_BASES = ["https://api.kolada.se/v3", "https://api.kolada.se/v2"]
HTTP_TIMEOUT = 60
USER_AGENT = "kommun-school-benchmark (portfolio project; github.com/davka99)"

# Spring terms covered by the analysis window (grade-9 leavers). Confirmed or narrowed in M2.
YEARS = list(range(2015, 2026))
PROBE_YEAR = 2024

# Free-text searches used by the probe to list candidate KPIs. The final KPI list is
# frozen in docs/decisions.md (M2) before any model is fitted.
KPI_SEARCH_TERMS = [
    "meritvärde",
    "behöriga till yrkesprogram",
    "modellberäknat",
    "eftergymnasial utbildning",
    "nyinvandrade",
    "utländsk bakgrund",
    "elever i åk 9",
    "elever i årskurs 9",
    "pojkar",
]
# A candidate KPI must mention grade 9 to be coverage-checked in the probe.
GRADE9_MARKERS = ["åk 9", "årskurs 9", "åk. 9", "år 9"]
MAX_COVERAGE_CHECKS = 40

# SCB open geodata. DeSO codes start with the 4-digit municipality code, so the
# municipality layer is DeSO dissolved by code[:4]. CC0 licence.
SCB_DESO_PAGES = [
    "https://www.scb.se/vara-tjanster/oppna-data/oppna-geodata/demografiska-statistikomraden-deso/",
    "https://www.scb.se/hitta-statistik/regional-statistik-och-kartor/geodata/oppna-geodata/deso--demografiska-statistikomraden/",
]
# Fallback if the SCB file cannot be found: community GeoJSON derived from SCB data.
GEO_FALLBACK_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_municipalities.geojson"
)
GEO_SIMPLIFY_M = 200  # metres, SWEREF 99 TM; for figures only

N_MUNICIPALITIES = 290
STOCKHOLM_COUNTY = "01"
