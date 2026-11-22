"""
Parser for public-body sale notices (avvisi d'asta / alienazioni).

Input is the plain text of one notice (Gazzetta Ufficiale 5a serie, an ente's
own page, …). Output is a list of records — one per lot — in the same
``{"property_data", "auction_data"}`` shape produced by the PVP parser, so the
ingestion pipeline (upsert → ROI → risk) handles both sources identically.

Pure functions, no I/O: everything here is unit-testable on fixture text.
Notices are free text written by thousands of different offices, so every
field is best-effort; what could not be parsed is left as None.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.core import geo_it

_TZ = ZoneInfo("Europe/Rome")

_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

# ── Relevance ─────────────────────────────────────────────────────────────────

_SALE_RE = re.compile(
    r"\b(vendita|alienazion\w*|alienare|cessione|dismission\w*|asta pubblica)\b", re.I
)
_NOT_SALE_RE = re.compile(
    r"\b(locazion\w*|concession\w*|affitt\w*|esito|aggiudicazione definitiva|"
    r"comodato|servizi\w*|fornitur\w*|lavori)\b",
    re.I,
)
_REAL_ESTATE_RE = re.compile(
    r"\b(immobil\w*|terren\w*|fabbricat\w*|appartament\w*|unit[aà] immobiliar\w*|"
    r"area|aree|alloggi\w*|locale|locali|magazzin\w*|box|autorimess\w*|capannon\w*|"
    r"villa|edifici\w*|compendio|lotto|lotti|negozi\w*|uffici\w*)\b",
    re.I,
)


def is_real_estate_sale(title: str, body: str) -> bool:
    """True for notices that sell real estate (not leases, concessions, results)."""
    head = f"{title}\n{body[:600]}"
    if not _SALE_RE.search(head):
        return False
    # A notice can mention "concessione" in passing; only the title decides that.
    if _NOT_SALE_RE.search(title) and not _SALE_RE.search(title):
        return False
    return bool(_REAL_ESTATE_RE.search(f"{title}\n{body}"))


# ── Field extractors ──────────────────────────────────────────────────────────

_AMOUNT = r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
_PRICE_RES = [
    # "prezzo (a) base (d'asta) di € 92.750,00", "importo a base di gara: € 80.000,00"
    re.compile(
        r"(?:prezzo|importo|valore)\s+(?:posto\s+)?(?:a\s+)?base(?:\s+d['’]?\s*asta|\s+di\s+gara|\s+d['’]?\s*incanto)?"
        r"[^€\d]{0,40}?(?:€|euro|eur)\s*" + _AMOUNT,
        re.I,
    ),
    # "Prezzo base: 2.625,00 €"
    re.compile(
        r"(?:prezzo|importo)\s+(?:a\s+)?base[^€\d]{0,30}?" + _AMOUNT + r"\s*(?:€|euro)",
        re.I,
    ),
    # "base d'asta € 98.000,00"
    re.compile(r"base\s+d['’]?\s*asta[^€\d]{0,20}?(?:€|euro)\s*" + _AMOUNT, re.I),
]


def parse_amount(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def extract_price(text: str) -> Optional[Decimal]:
    for rx in _PRICE_RES:
        m = rx.search(text)
        if m:
            value = parse_amount(m.group(1))
            if value is not None:
                return value
    return None


_DATE_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_TXT = re.compile(
    r"\b(\d{1,2})(?:°|º)?\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.I
)
_TIME = re.compile(r"\b(?:ore|alle ore)\s+(\d{1,2})[:.](\d{2})\b", re.I)


def _dates_with_pos(text: str) -> list[tuple[int, int, datetime]]:
    """All dates in text with (start, end, value); time attached when it follows."""
    found = []
    for m in _DATE_NUM.finditer(text):
        d, mo, y = (int(x) for x in m.groups())
        found.append((m.start(), m.end(), d, mo, y))
    for m in _DATE_TXT.finditer(text):
        found.append((m.start(), m.end(), int(m.group(1)), _MONTHS[m.group(2).lower()],
                      int(m.group(3))))
    out = []
    for start, end, d, mo, y in found:
        try:
            dt = datetime(y, mo, d, tzinfo=_TZ)
        except ValueError:
            continue
        # time just before ("ore 12:00 del 03/08/2026") or just after ("… 2026 ore 10.00")
        window = text[max(0, start - 30): end + 35]
        t = _TIME.search(window)
        if t and 0 <= int(t.group(1)) < 24:
            dt = dt.replace(hour=int(t.group(1)), minute=int(t.group(2)))
        out.append((start, end, dt))
    return sorted(out, key=lambda x: x[0])


_DEADLINE_CUE = re.compile(
    r"(entro|termine|scadenza|pervenire|presentazione delle offerte|ricevimento delle offerte)",
    re.I,
)
_AUCTION_CUE = re.compile(
    r"(avr(?:a['’]|à|a)\s+luogo|seduta pubblica|apertura (?:delle )?(?:buste|offerte|plichi)|"
    r"si terr(?:a['’]|à|a)|gara si svolger(?:a['’]|à|a))",
    re.I,
)


def _date_near(
    text: str, cue: re.Pattern, reference: datetime, before: int = 160, after: int = 160
) -> Optional[datetime]:
    """
    Closest plausible date around a cue word. Dates far from the publication
    date (e.g. "R.D. 23 maggio 1924", a council resolution from last year) are
    ignored.
    """
    dates = [
        (start, end, dt) for start, end, dt in _dates_with_pos(text)
        if abs((dt - reference).days) <= 400
    ]
    best: Optional[tuple[int, datetime]] = None
    for m in cue.finditer(text):
        for start, end, dt in dates:
            if start >= m.end():
                gap = start - m.end()
                ok = gap <= after
            else:
                gap = m.start() - end
                ok = 0 <= gap <= before
            if ok and (best is None or gap < best[0]):
                best = (gap, dt)
        if best:
            return best[1]
    return None


def extract_dates(
    text: str, reference: Optional[datetime] = None
) -> tuple[Optional[datetime], Optional[datetime]]:
    """(auction/opening date, offer deadline), relative to the publication date."""
    reference = reference or datetime.now(_TZ)
    return (
        _date_near(text, _AUCTION_CUE, reference),
        _date_near(text, _DEADLINE_CUE, reference, before=0),
    )


_SQM = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)\s*(?:mq|m2|m²|metri quadr\w*)\b",
                  re.I)


def extract_area(text: str) -> Optional[Decimal]:
    m = _SQM.search(text)
    return parse_amount(m.group(1)) if m else None


_TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("land", re.compile(r"\b(terren\w*|area edificabil\w*|aree?\b|relitt\w*|fondo agricol\w*|"
                        r"lotto edificabil\w*)", re.I)),
    ("garage", re.compile(r"\b(box|autorimess\w*|posti? auto|garage)\b", re.I)),
    ("industrial", re.compile(r"\b(capannon\w*|opificio|industrial\w*|artigianal\w*)\b", re.I)),
    ("commercial", re.compile(r"\b(negozi\w*|locale commercial\w*|locali commercial\w*|"
                              r"uffici\w*|chiosco|c/1)\b", re.I)),
    ("villa", re.compile(r"\b(villa|villino|villetta)\b", re.I)),
    ("apartment", re.compile(r"\b(appartament\w*|alloggi\w*|unit[aà] (?:immobiliare )?"
                             r"(?:ad uso )?abitativ\w*|abitazion\w*|a/[1-9]|"
                             r"unit[aà] immobiliar\w*[^;]{0,100}?\bpiano\b)", re.I)),
]


def classify(text: str) -> str:
    for ptype, rx in _TYPE_RULES:
        if rx.search(text):
            return ptype
    return "other"


_ADDRESS = re.compile(
    r"\b((?i:via|viale|corso|piazza|piazzale|largo|vicolo|strada|localit[aà]|frazione))\s+"
    r"((?:[A-ZÀ-Ý][\wÀ-ÿ'’.]*|[IVXLC]+|\d{1,2}|d[eia]l?l?[aeoi]?|di|de|del|della|dei|degli|delle)"
    r"(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’.]*|[IVXLC]+|\d{1,2}|d[eia]l?l?[aeoi]?|di|de|del|della|dei|degli|delle)){0,6})"
    r"(?:\s*,?\s*(?:n\.?\s*)?(\d{1,4}\s?[a-zA-Z]?\b|(?i:snc)))?",
)


def extract_address(text: str, exclude: str = "") -> Optional[str]:
    """
    First street address in ``text``. Addresses that also appear in ``exclude``
    (the selling body's own seat, where the auction is held) are skipped.
    """
    excluded = geo_it.normalize(exclude)
    for m in _ADDRESS.finditer(text):
        name = " ".join(w for w in geo_it.normalize(m.group(2)).split() if not w.isdigit())
        if excluded and name and name in excluded:
            continue
        street = f"{m.group(1).capitalize()} {m.group(2)}"
        if m.group(3):
            street += f" {m.group(3)}"
        return re.sub(r"\s+", " ", street).strip(" ,.")
    return None


def extract_location(
    lot_text: str, notice_text: str, ente: str, sede: str
) -> Optional[geo_it.Comune]:
    """
    Where the property is, most specific first:
    1. "sito/ubicato in (Comune di) X" in the lot, then in the whole notice
    2. "Comune di X" in the lot
    3. the selling body when it is itself a Comune ("COMUNE DI MOMO")
    4. the city in the body's address ("Sede: … - 28015 Momo")
    """
    hint = geo_it.province_from_text(lot_text) or geo_it.province_from_text(notice_text)
    located = r"\b(?:sit[oaie]|ubicat[oaie]|posto|posta|localizzat[oaie])\s+(?:nel\s+|in\s+)?(?:comune\s+di\s+)?"
    for text in (lot_text, notice_text):
        hit = geo_it.find_after(text, located, hint)
        if hit:
            return hit
    hit = geo_it.find_after(lot_text, r"\bcomune\s+di\s+", hint)
    if hit:
        return hit
    hit = geo_it.find_after(ente, r"^\s*comune\s+di\s+", hint)
    if hit:
        return hit
    return geo_it.find_after(sede, r"\b\d{5}\s+", hint)


_LOT_SPLIT = re.compile(r"(?=\blotto\s*(?:n\.?|numero)?\s*\d+\b)", re.I)
_LOT_NUM = re.compile(r"\blotto\s*(?:n\.?|numero)?\s*(\d+)", re.I)


def split_lots(body: str) -> list[tuple[Optional[str], str]]:
    """[(lot number, lot text)]; a single (None, body) when there are no lots."""
    parts = [p for p in _LOT_SPLIT.split(body) if p.strip()]
    lots = []
    for part in parts:
        m = _LOT_NUM.match(part.strip())
        if m:
            lots.append((m.group(1), part))
    # Keep lots only when each one carries its own price; otherwise the notice
    # merely mentions "lotto unico" and is treated as one sale.
    if len(lots) > 1 and sum(1 for _, t in lots if extract_price(t)) >= 2:
        # dedupe repeated lot numbers (summary table + detail)
        seen: dict[str, str] = {}
        for num, text in lots:
            if num not in seen or (extract_price(text) and not extract_price(seen[num])):
                seen[num] = text
        return list(seen.items())
    return [(None, body)]


# ── Public entry point ────────────────────────────────────────────────────────

def parse_notice(
    *,
    notice_id: str,
    source: str,
    title: str,
    body: str,
    ente: str,
    sede: str = "",
    url: Optional[str] = None,
    published: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Turn one notice into per-lot records. Returns [] when it is not a sale."""
    if not is_real_estate_sale(title, body):
        return []

    now = now or datetime.now(_TZ)
    auction_date, deadline = extract_dates(body, published or now)
    when = auction_date or deadline
    status = "scheduled" if (when is None or when >= now) else "completed"

    records = []
    for lot_no, lot_text in split_lots(body):
        location = extract_location(lot_text, body, ente, sede)
        external_id = f"{notice_id}-{lot_no}" if lot_no else notice_id
        description = re.sub(r"\s+", " ", f"{title}. {lot_text}").strip()[:4000]
        price = extract_price(lot_text) or (extract_price(body) if lot_no is None else None)
        records.append({
            "property_data": {
                "external_id": external_id,
                "source": source,
                "address": extract_address(lot_text, exclude=sede),
                "city": location.name if location else None,
                "province": location.province if location else None,
                "region": location.region if location else None,
                "property_type": classify(lot_text if lot_no else f"{title} {body}"),
                "area_sqm": extract_area(lot_text),
                "description": description,
                "extra": {"seller": ente, "notice_title": title, "lot": lot_no},
            },
            "auction_data": {
                "external_id": external_id,
                "source": source,
                "court": ente[:256] if ente else None,   # selling body
                "procedure_number": notice_id,
                "auction_type": "tradizionale",
                "status": status,
                "base_price": price,
                "auction_date": when,
                "auction_deadline": deadline,
                "publication_date": published,
                "source_url": url,
                "legal_notes": None,
            },
        })
    return records
