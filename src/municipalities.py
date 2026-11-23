"""Municipality codes (kommunkoder). A kommun code is 4 digits: county (län) + 2 digits.

Kolada also uses 4-digit ids for the whole country ("0000") and for regions
("0001".."0025"); those start with "00" and are not municipalities.
"""

from __future__ import annotations

import re

_KOMMUN = re.compile(r"^(0[1-9]|1[0-9]|2[0-5])\d{2}$")

COUNTIES = {
    "01": "Stockholm", "03": "Uppsala", "04": "Södermanland", "05": "Östergötland",
    "06": "Jönköping", "07": "Kronoberg", "08": "Kalmar", "09": "Gotland",
    "10": "Blekinge", "12": "Skåne", "13": "Halland", "14": "Västra Götaland",
    "17": "Värmland", "18": "Örebro", "19": "Västmanland", "20": "Dalarna",
    "21": "Gävleborg", "22": "Västernorrland", "23": "Jämtland", "24": "Västerbotten",
    "25": "Norrbotten",
}


def is_kommun(code) -> bool:
    c = str(code)
    return bool(_KOMMUN.match(c)) and c[:2] in COUNTIES


def county_of(code) -> str:
    c = str(code).zfill(4)
    if not is_kommun(c):
        raise ValueError(f"not a municipality code: {code!r}")
    return c[:2]


def kommun_from_deso(deso: str) -> str:
    """DeSO codes look like '0114A0010': the first four characters are the kommun code."""
    d = str(deso).strip()
    if len(d) != 9 or not is_kommun(d[:4]):
        raise ValueError(f"not a DeSO code: {deso!r}")
    return d[:4]
