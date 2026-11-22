"""
Italian municipality lookup (ISTAT list, bundled in app/data/comuni_istat.json).

Used to turn free-text locations in public notices ("immobile sito in Comune
di Varallo", "Sede: … - 28015 Momo") into a canonical city + province code.
Pure Python, no I/O after the first (cached) load.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "comuni_istat.json"


@dataclass(frozen=True)
class Comune:
    name: str
    province: str   # sigla, e.g. "MI"
    region: str


def normalize(text: str) -> str:
    """Lower-case, strip accents, unify apostrophes/hyphens, collapse spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[-–/]", " ", text)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def _index() -> dict[str, list[Comune]]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    idx: dict[str, list[Comune]] = {}
    for name, sigla, region in raw["comuni"]:
        comune = Comune(name=name, province=sigla, region=region)
        # Bilingual names ("Bolzano/Bozen") are indexed under each part too.
        for variant in {name, *name.split("/")}:
            idx.setdefault(normalize(variant), []).append(comune)
    return idx


@lru_cache(maxsize=1)
def _max_words() -> int:
    return max(len(k.split()) for k in _index())


def lookup(name: str, province_hint: Optional[str] = None) -> Optional[Comune]:
    """Exact (normalised) match. Ambiguous names need a province hint."""
    matches = _index().get(normalize(name), [])
    if province_hint:
        hinted = [c for c in matches if c.province == province_hint.upper()]
        if hinted:
            return hinted[0]
    return matches[0] if len(matches) == 1 else None


def find_after(text: str, pattern: str, province_hint: Optional[str] = None) -> Optional[Comune]:
    """
    Find the first comune named right after a regex ``pattern`` (e.g.
    r"comune di"), trying the longest word sequence first so that
    "San Giorgio su Legnano" wins over "San Giorgio".
    """
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        words = normalize(text[m.end(): m.end() + 80]).split()
        for n in range(min(_max_words(), len(words)), 0, -1):
            hit = lookup(" ".join(words[:n]), province_hint)
            if hit:
                return hit
    return None


def province_from_text(text: str) -> Optional[str]:
    """A '(MI)'-style province code, if present and valid."""
    valid = {c.province for comuni in _index().values() for c in comuni}
    for code in re.findall(r"\(([A-Z]{2})\)", text):
        if code in valid:
            return code
    return None
