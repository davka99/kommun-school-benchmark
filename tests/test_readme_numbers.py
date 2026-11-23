import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_readme", Path(__file__).resolve().parents[1] / "scripts" / "check_readme.py")
cr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cr)


def test_every_readme_number_matches_reports():
    text = (cr.ROOT / "README.md").read_text(encoding="utf-8")
    missing = [(k, s) for k, s in cr.expected_strings() if s not in text]
    assert not missing, missing
