"""
Opportunity parser — converts raw text or JSON into structured PublicOpportunity dicts.

Classifies opportunity type by keyword matching against Italian public document
vocabulary, then extracts location, budget, and timeline signals.

Public entry-point:
  parse_opportunity(raw: dict | str, *, source: str) -> dict | None
  Returns a dict ready to pass to PublicOpportunityRepository.upsert(), or None
  when the input cannot be meaningfully classified.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

# ── Keyword taxonomy ──────────────────────────────────────────────────────────
# Maps OpportunityType enum values → Italian trigger words

_TYPE_KEYWORDS: dict[str, list[str]] = {
    "rigenerazione_urbana": [
        "rigenerazione urbana", "riqualificazione urbana", "recupero urbano",
        "rinnovamento urbano", "riabilitazione urbana", "riconversione urbana",
        "quartiere sostenibile",
    ],
    "pnrr_progetto": [
        "pnrr", "piano nazionale di ripresa", "next generation eu", "ngeu",
        "resilienza e ripresa", "misura m1", "misura m2", "misura m3",
    ],
    "investimento_infrastrutturale": [
        "infrastruttura", "opera pubblica", "intervento infrastrutturale",
        "mobilità urbana", "metropolitana", "asse viario", "tangenziale",
        "ferrovia", "porto", "aeroporto", "parco tecnologico",
    ],
    "piano_recupero": [
        "piano di recupero", "piano attuativo", "recupero edilizio",
        "riqualificazione edilizia", "programma integrato", "contratto di quartiere",
    ],
    "piano_urbanistico": [
        "piano regolatore", "piano urbanistico", "prg", "pgt", "puc",
        "variante urbanistica", "piano territoriale", "norme tecniche di attuazione",
        "zona omogenea",
    ],
    "alienazione_pubblica": [
        "alienazione", "cessione immobile", "vendita immobile comunale",
        "patrimonio pubblico", "dismissione patrimonio", "asta pubblica",
        "bando di vendita", "offerta di acquisto",
    ],
    "dismissione_pubblica": [
        "dismissione", "dismesso", "ex caserma", "ex ospedale", "ex carcere",
        "ex area industriale", "ex sede", "heritage building",
    ],
    "valorizzazione_immobiliare": [
        "valorizzazione immobiliare", "valorizzazione patrimoniale",
        "project financing", "partenariato pubblico privato", "ppp",
        "concessione valorizzazione",
    ],
}

_PROVINCE_CODE_RE = re.compile(r"\b([A-Z]{2})\b")
_BUDGET_RE = re.compile(
    r"(?:€\s*|EUR\s*|euro\s*)([\d]{1,3}(?:[.\s][\d]{3})*(?:,\d{1,2})?)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


# ── Public entry point ────────────────────────────────────────────────────────

def parse_opportunity(raw: dict | str, *, source: str = "unknown") -> Optional[dict]:
    """
    Parse raw discovery data into a dict suitable for PublicOpportunityRepository.upsert().

    raw may be:
      dict  — structured JSON from an API response
      str   — free-form text (from PDF extraction, HTML scraping, etc.)

    Returns None when no meaningful classification can be made.
    """
    if isinstance(raw, dict):
        return _parse_dict(raw, source=source)
    if isinstance(raw, str):
        return _parse_text(raw, source=source)
    return None


# ── Dict parser ───────────────────────────────────────────────────────────────

def _parse_dict(data: dict, *, source: str) -> Optional[dict]:
    title = (
        data.get("title")
        or data.get("titolo")
        or data.get("name")
        or data.get("nome")
        or data.get("oggetto")
        or ""
    ).strip()
    if not title:
        return None

    description = (
        data.get("description")
        or data.get("descrizione")
        or data.get("abstract")
        or data.get("testo")
        or ""
    )
    combined_text = f"{title} {description}".lower()

    opp_type = _classify_type(combined_text)
    province = _extract_province(data, combined_text)
    city = (
        data.get("city") or data.get("citta") or data.get("comune") or ""
    ).strip() or None
    budget = _extract_budget_dict(data) or _extract_budget_text(combined_text)
    completion = _extract_completion(data, combined_text)

    return {
        "title": title,
        "opportunity_type": opp_type,
        "source": source,
        "source_url": data.get("url") or data.get("link") or data.get("source_url"),
        "province": province,
        "city": city,
        "description": str(description)[:2000] if description else None,
        "budget_amount": budget,
        "expected_completion": completion,
        "document_url": data.get("document_url") or data.get("pdf_url") or data.get("allegato"),
        "raw_text": combined_text[:4000],
        "extra": {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))},
    }


# ── Text parser ───────────────────────────────────────────────────────────────

def _parse_text(text: str, *, source: str) -> Optional[dict]:
    if len(text.strip()) < 30:
        return None

    lower = text.lower()
    opp_type = _classify_type(lower)
    if opp_type == "altro" and len(text) < 100:
        return None  # too short and unclassifiable — skip

    title = _extract_title_from_text(text)
    province = _extract_province_from_text(text)
    budget = _extract_budget_text(lower)
    completion = _extract_completion_from_text(text)

    return {
        "title": title,
        "opportunity_type": opp_type,
        "source": source,
        "source_url": None,
        "province": province,
        "city": None,
        "description": text[:2000],
        "budget_amount": budget,
        "expected_completion": completion,
        "document_url": None,
        "raw_text": text[:4000],
        "extra": {"parse_method": "text"},
    }


# ── Classification ────────────────────────────────────────────────────────────

def _classify_type(text: str) -> str:
    scores: dict[str, int] = {}
    for opp_type, keywords in _TYPE_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw in text)
        if hit:
            scores[opp_type] = hit
    if not scores:
        return "altro"
    return max(scores, key=lambda k: scores[k])


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_province(data: dict, text: str) -> Optional[str]:
    for key in ("province", "provincia", "prov"):
        v = data.get(key)
        if v and isinstance(v, str) and len(v.strip()) <= 4:
            return v.strip().upper()
    return _extract_province_from_text(text)


def _extract_province_from_text(text: str) -> Optional[str]:
    matches = _PROVINCE_CODE_RE.findall(text.upper())
    # Return the first 2-letter code that looks like a province (heuristic)
    known_prefixes = {
        "AG", "AL", "AN", "AO", "AP", "AQ", "AR", "AT", "AV", "BA", "BG",
        "BI", "BL", "BN", "BO", "BR", "BS", "BT", "BZ", "CA", "CB", "CE",
        "CH", "CL", "CN", "CO", "CR", "CS", "CT", "CZ", "EN", "FC", "FE",
        "FG", "FI", "FM", "FR", "GE", "GO", "GR", "IM", "IS", "KR", "LC",
        "LE", "LI", "LO", "LT", "LU", "MB", "MC", "ME", "MI", "MN", "MO",
        "MS", "MT", "NA", "NO", "NU", "OR", "PA", "PC", "PD", "PE", "PG",
        "PI", "PN", "PO", "PR", "PT", "PU", "PV", "PZ", "RA", "RC", "RE",
        "RG", "RI", "RM", "RN", "RO", "SA", "SI", "SO", "SP", "SR", "SS",
        "SU", "SV", "TA", "TE", "TN", "TO", "TP", "TR", "TS", "TV", "UD",
        "VA", "VB", "VC", "VE", "VI", "VR", "VT", "VV",
    }
    for code in matches:
        if code in known_prefixes:
            return code
    return None


def _extract_budget_dict(data: dict) -> Optional[Decimal]:
    for key in ("budget", "importo", "valore", "finanziamento", "costo", "amount"):
        v = data.get(key)
        if v is not None:
            try:
                return Decimal(str(v).replace(".", "").replace(",", ".").strip())
            except InvalidOperation:
                continue
    return None


def _extract_budget_text(text: str) -> Optional[Decimal]:
    for m in _BUDGET_RE.finditer(text):
        raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
        try:
            val = Decimal(raw)
            if val > 1000:  # ignore trivially small amounts
                return val
        except InvalidOperation:
            continue
    return None


def _extract_completion(data: dict, text: str) -> Optional[str]:
    for key in ("completion", "scadenza", "fine_lavori", "data_fine", "anno_completamento"):
        v = data.get(key)
        if v:
            return str(v)[:64]
    return _extract_completion_from_text(text)


def _extract_completion_from_text(text: str) -> Optional[str]:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else None


def _extract_title_from_text(text: str) -> str:
    """Use the first non-empty line (up to 200 chars) as the title."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 10:
            return line[:200]
    return text[:100].strip()
