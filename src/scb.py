"""SCB PxWeb (API v1) helpers: browse the table tree and read table metadata."""

from __future__ import annotations

import re
import time
from typing import Callable

SCB_BASE = "https://api.scb.se/OV0104/v1/doris/sv/ssd"


def parse_node_list(payload) -> list[dict]:
    """A PxWeb folder listing: [{'id','type','text'}]; type 'l' = folder, 't' = table."""
    if not isinstance(payload, list):
        raise ValueError(f"PxWeb folder listing must be a list, got {type(payload).__name__}")
    out = []
    for item in payload:
        if "id" not in item or "type" not in item:
            raise ValueError(f"PxWeb node without id/type: {item}")
        out.append({"id": item["id"], "type": item["type"], "text": item.get("text", "")})
    return out


def browse(get: Callable[[str], object], start_paths: list[str], pattern: str, max_depth: int = 3,
           max_requests: int = 150, pause: float = 0.4) -> tuple[list[dict], list[str]]:
    """Breadth-first walk from `start_paths`; return tables whose text or path matches `pattern`.

    Folders are only expanded if their own text matches `pattern` or they are within the
    first two levels, which keeps the walk small. Returns (tables, errors).
    """
    rx = re.compile(pattern, re.I)
    queue = [(p.strip("/"), 0) for p in start_paths]
    tables, errors, n = [], [], 0
    while queue and n < max_requests:
        path, depth = queue.pop(0)
        n += 1
        try:
            nodes = parse_node_list(get(f"{SCB_BASE}/{path}"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {exc}"[:300])
            continue
        finally:
            time.sleep(pause)
        for node in nodes:
            child = f"{path}/{node['id']}"
            if node["type"] == "t":
                if rx.search(node["text"]) or rx.search(child):
                    tables.append({"path": child, "text": node["text"]})
            elif node["type"] == "l" and depth + 1 <= max_depth and (depth < 2 or rx.search(node["text"])):
                queue.append((child, depth + 1))
    return tables, errors


def summarise_metadata(meta: dict) -> dict:
    """Variables of a PxWeb table with value counts and a few example labels."""
    out = {"title": meta.get("title"), "variables": []}
    for v in meta.get("variables", []):
        labels = v.get("valueTexts", [])
        out["variables"].append({
            "code": v.get("code"), "text": v.get("text"), "n_values": len(v.get("values", [])),
            "examples": labels[:6], "time": bool(v.get("time")),
            "last": labels[-1] if labels else None,
        })
    return out


def px_to_frame(meta: dict, result: dict):
    """Turn a PxWeb v1 JSON result into a DataFrame with value *texts* (not codes)."""
    import pandas as pd

    labels = {v["code"]: dict(zip(v.get("values", []), v.get("valueTexts", []))) for v in meta["variables"]}
    dims = [c for c in result["columns"] if c.get("type") != "c"]
    measures = [c for c in result["columns"] if c.get("type") == "c"]
    rows = []
    for rec in result["data"]:
        row = {d["code"]: labels.get(d["code"], {}).get(k, k) for d, k in zip(dims, rec["key"])}
        for m, v in zip(measures, rec["values"]):
            row[m["code"]] = pd.to_numeric(v, errors="coerce")
        rows.append(row)
    return pd.DataFrame(rows)


def school_year_to_spring(label: str) -> int:
    """'2014/15' -> 2015 (the spring term in which grade 9 ends)."""
    a, b = str(label).split("/")
    return int(a) + 1


def select_all_query(meta: dict) -> dict:
    """PxWeb v1 query selecting every value of every variable.

    An empty query lets PxWeb *eliminate* optional variables (it summed away
    'SvUtlBakgrund' in Tema42 and returned empty means), so every variable is listed.
    """
    return {"query": [{"code": v["code"], "selection": {"filter": "all", "values": ["*"]}}
                      for v in meta["variables"]],
            "response": {"format": "json"}}
