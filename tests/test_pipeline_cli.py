import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "run_pipeline", Path(__file__).resolve().parents[1] / "scripts" / "run_pipeline.py")
rp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rp)


def test_unknown_stage_is_rejected():
    with pytest.raises(SystemExit, match="unknown"):
        rp.main(["probe", "nope"])
    with pytest.raises(SystemExit, match="usage"):
        rp.main([])


def test_detect_base_falls_back_to_v2():
    def get(url):
        if "/v3/" in url:
            raise RuntimeError("HTTP 404")
        return {"count": 1, "values": [{"id": "N1", "title": "t"}]}

    base, tried = rp._detect_base(get)
    assert base.endswith("/v2")
    assert tried["https://api.kolada.se/v3"]["ok"] is False


def test_detect_base_rejects_unexpected_shape():
    with pytest.raises(RuntimeError, match="no Kolada API"):
        rp._detect_base(lambda url: {"data": []})
