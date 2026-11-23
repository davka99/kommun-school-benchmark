"""Small Kolada API client and parsers.

The parsers accept both the v2 and the v3 response shapes seen in public clients:
a dict with ``values`` and an optional ``next_page`` / ``next_url`` link. They fail
loudly when a core field is missing instead of guessing.
"""

from __future__ import annotations

import time
import unicodedata
from typing import Callable, Iterable, Iterator
from urllib.parse import quote

import pandas as pd

Getter = Callable[[str], dict]

KPI_FIELDS = [
    "id",
    "title",
    "description",
    "operating_area",
    "municipality_type",
    "is_divided_by_gender",
    "has_ou_data",
    "publ_period",
]
DATA_COLUMNS = ["kpi", "municipality", "period", "gender", "value", "count", "status"]


class KoladaSchemaError(ValueError):
    """Raised when a payload lacks a field the analysis depends on."""


def make_getter(session=None, timeout: int = 60, user_agent: str = "", retries: int = 3) -> Getter:
    """Return a JSON getter with simple retry/backoff (network stages only)."""
    import requests

    s = session or requests.Session()
    if user_agent:
        s.headers["User-Agent"] = user_agent

    def get(url: str) -> dict:
        last = None
        for attempt in range(retries):
            try:
                r = s.get(url, timeout=timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised
                last = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")

    return get


def next_link(payload: dict) -> str | None:
    for key in ("next_page", "next_url", "next"):
        v = payload.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def paginate(first_url: str, get: Getter, max_pages: int = 500) -> Iterator[dict]:
    """Yield every page, following next links. Stops on a repeated link."""
    url, seen = first_url, set()
    for _ in range(max_pages):
        if url in seen:
            raise RuntimeError(f"pagination loop at {url}")
        seen.add(url)
        payload = get(url)
        if not isinstance(payload, dict) or "values" not in payload:
            raise KoladaSchemaError(f"no 'values' in response from {url}")
        yield payload
        url = next_link(payload)
        if url is None:
            return
    raise RuntimeError(f"more than {max_pages} pages from {first_url}")


def kpi_search_url(base: str, term: str) -> str:
    return f"{base}/kpi?title={quote(term)}"


def data_url(base: str, kpi_ids: Iterable[str], years: Iterable[int]) -> str:
    k = ",".join(kpi_ids)
    y = ",".join(str(int(v)) for v in years)
    return f"{base}/data/kpi/{k}/year/{y}"


def municipality_url(base: str) -> str:
    return f"{base}/municipality"


def parse_kpis(payloads: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for p in payloads:
        for v in p["values"]:
            if "id" not in v or "title" not in v:
                raise KoladaSchemaError(f"KPI record without id/title: {sorted(v)}")
            rows.append({f: v.get(f) for f in KPI_FIELDS})
    df = pd.DataFrame(rows, columns=KPI_FIELDS)
    return df.drop_duplicates("id").reset_index(drop=True)


def parse_data(payloads: Iterable[dict]) -> pd.DataFrame:
    """Flatten data payloads to one row per kpi x municipality x period x gender.

    Missing values are kept as NaN (with their status) so suppression can be counted.
    """
    rows = []
    for p in payloads:
        for rec in p["values"]:
            for key in ("kpi", "municipality", "period", "values"):
                if key not in rec:
                    raise KoladaSchemaError(f"data record without '{key}': {sorted(rec)}")
            for val in rec["values"]:
                if "gender" not in val or "value" not in val:
                    raise KoladaSchemaError(f"value without gender/value: {sorted(val)}")
                rows.append(
                    {
                        "kpi": str(rec["kpi"]),
                        "municipality": str(rec["municipality"]).zfill(4),
                        "period": int(rec["period"]),
                        "gender": val["gender"],
                        "value": val["value"],
                        "count": val.get("count"),
                        "status": val.get("status") or "",
                    }
                )
    df = pd.DataFrame(rows, columns=DATA_COLUMNS)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def parse_municipalities(payloads: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for p in payloads:
        for v in p["values"]:
            if "id" not in v:
                raise KoladaSchemaError("municipality record without id")
            rows.append({"id": str(v["id"]), "title": v.get("title"), "type": v.get("type")})
    return pd.DataFrame(rows, columns=["id", "title", "type"]).drop_duplicates("id")


def _fold(s: str) -> str:
    """Lower-case; keep å/ä/ö (they matter in Swedish) but normalise composed forms."""
    return unicodedata.normalize("NFC", s or "").lower()


def grade9_candidates(kpis: pd.DataFrame, markers: Iterable[str]) -> pd.DataFrame:
    """KPIs whose title mentions grade 9, municipality level (not unit-only)."""
    marks = [_fold(m) for m in markers]
    title = kpis["title"].fillna("").map(_fold)
    hit = title.map(lambda t: any(m in t for m in marks))
    mtype = kpis["municipality_type"].fillna("K").astype(str)
    level_ok = mtype.str.contains("K") | mtype.str.contains("A")
    return kpis[hit & level_ok].sort_values("id").reset_index(drop=True)


def coverage(data: pd.DataFrame, gender: str = "T") -> pd.DataFrame:
    """Per KPI and period: municipalities with a value, missing and status codes."""
    from municipalities import is_kommun

    d = data[(data["gender"] == gender) & data["municipality"].map(is_kommun)]
    g = d.groupby(["kpi", "period"])
    out = g.agg(
        n_rows=("value", "size"),
        n_values=("value", lambda s: int(s.notna().sum())),
        mean=("value", "mean"),
        min=("value", "min"),
        max=("value", "max"),
    ).reset_index()
    status = d[d["status"] != ""].groupby(["kpi", "period"])["status"].agg(
        lambda s: ";".join(sorted(set(s)))
    )
    out["statuses"] = out.set_index(["kpi", "period"]).index.map(status).fillna("")
    return out
