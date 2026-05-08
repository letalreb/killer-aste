"""
Parser for the PVP REST API JSON responses.

Endpoint: POST /ric-496b258c-986a1b71/ric-ms/ricerca/vendite
Response: {"messaggio": "...", "body": {Spring Page}}

Each page record is mapped to (property_data, auction_data) dicts
ready for upsert into the DB.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# ── Province full-name → 2-letter ISTAT code ─────────────────────────────────
_PROVINCIA_CODE: dict[str, str] = {
    "Agrigento": "AG", "Alessandria": "AL", "Ancona": "AN", "Aosta": "AO",
    "Arezzo": "AR", "Ascoli Piceno": "AP", "Asti": "AT", "Avellino": "AV",
    "Bari": "BA", "Barletta-Andria-Trani": "BT", "Belluno": "BL",
    "Benevento": "BN", "Bergamo": "BG", "Biella": "BI", "Bologna": "BO",
    "Bolzano": "BZ", "Brescia": "BS", "Brindisi": "BR", "Cagliari": "CA",
    "Caltanissetta": "CL", "Campobasso": "CB", "Caserta": "CE",
    "Catania": "CT", "Catanzaro": "CZ", "Chieti": "CH", "Como": "CO",
    "Cosenza": "CS", "Cremona": "CR", "Crotone": "KR", "Cuneo": "CN",
    "Enna": "EN", "Fermo": "FM", "Ferrara": "FE", "Firenze": "FI",
    "Foggia": "FG", "Forlì-Cesena": "FC", "Frosinone": "FR",
    "Genova": "GE", "Gorizia": "GO", "Grosseto": "GR", "Imperia": "IM",
    "Isernia": "IS", "L'Aquila": "AQ", "La Spezia": "SP", "Latina": "LT",
    "Lecce": "LE", "Lecco": "LC", "Livorno": "LI", "Lodi": "LO",
    "Lucca": "LU", "Macerata": "MC", "Mantova": "MN", "Massa-Carrara": "MS",
    "Matera": "MT", "Messina": "ME", "Milano": "MI", "Modena": "MO",
    "Monza e della Brianza": "MB", "Napoli": "NA", "Novara": "NO",
    "Nuoro": "NU", "Oristano": "OR", "Padova": "PD", "Palermo": "PA",
    "Parma": "PR", "Pavia": "PV", "Perugia": "PG", "Pesaro e Urbino": "PU",
    "Pescara": "PE", "Piacenza": "PC", "Pisa": "PI", "Pistoia": "PT",
    "Pordenone": "PN", "Potenza": "PZ", "Prato": "PO", "Ragusa": "RG",
    "Ravenna": "RA", "Reggio Calabria": "RC", "Reggio Emilia": "RE",
    "Rieti": "RI", "Rimini": "RN", "Roma": "RM", "Rovigo": "RO",
    "Salerno": "SA", "Sassari": "SS", "Savona": "SV", "Siena": "SI",
    "Siracusa": "SR", "Sondrio": "SO", "Taranto": "TA", "Teramo": "TE",
    "Terni": "TR", "Torino": "TO", "Trapani": "TP", "Trento": "TN",
    "Treviso": "TV", "Trieste": "TS", "Udine": "UD", "Varese": "VA",
    "Venezia": "VE", "Verbano-Cusio-Ossola": "VB", "Vercelli": "VC",
    "Verona": "VR", "Vibo Valentia": "VV", "Vicenza": "VI", "Viterbo": "VT",
}

_CATEGORIA_BENE_TO_PROPERTY_TYPE: dict[str, str] = {
    "VILLA": "villa",
    "VILLETTA_SCHIERA": "villa",
    "VILLINO": "villa",
    "ABITAZIONE_TIPO_A": "apartment",
    "ABITAZIONE_TIPO_B": "apartment",
    "ABITAZIONE_TIPO_C": "apartment",
    "ABITAZIONE_TIPO_ECO": "apartment",
    "APPARTAMENTO": "apartment",
    "NEGOZIO": "commercial",
    "UFFICIO": "commercial",
    "LOCALE_COMMERCIALE": "commercial",
    "CAPANNONE": "industrial",
    "CAPANNONE_INDUSTRIALE": "industrial",
    "OPIFICIO": "industrial",
    "TERRENO": "land",
    "TERRENO_AGRICOLO": "land",
    "SUOLO": "land",
    "GARAGE": "garage",
    "BOX": "garage",
    "POSTO_AUTO": "garage",
}

_ESITO_TO_STATUS: dict[str | None, str] = {
    None: "scheduled",
    "AGGIUDICATO": "completed",
    "NON_AGGIUDICATO": "failed",
    "DESERTO": "failed",
    "SOSPESO": "suspended",
    "ANNULLATO": "cancelled",
}


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    log.warning("parser.date_parse_failed", raw=raw)
    return None


def _province_code(full_name: Optional[str]) -> Optional[str]:
    if not full_name:
        return None
    return _PROVINCIA_CODE.get(full_name.strip())


def _property_type(categorie: list[str]) -> str:
    for cat in categorie:
        pt = _CATEGORIA_BENE_TO_PROPERTY_TYPE.get(cat.upper())
        if pt:
            return pt
    return "other"


def _detect_encumbrances(desc: Optional[str]) -> Optional[str]:
    if not desc:
        return None
    desc_lower = desc.lower()
    found = [k for k in ("ipoteca", "pignoramento", "privilegio", "vincolo") if k in desc_lower]
    return ", ".join(found) if found else None


_SQM_RE = __import__("re").compile(r"(\d[\d.,]*)\s*m(?:q|²|2)\b", __import__("re").IGNORECASE)


def _extract_sqm(desc: Optional[str]) -> Optional[Decimal]:
    """Parse area from free-text description, e.g. '85 mq' or '120,5 m²'."""
    if not desc:
        return None
    m = _SQM_RE.search(desc)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    return _to_decimal(raw)


def parse_api_response(data: dict) -> list[dict]:
    """
    Parse one page of the PVP /ricerca/vendite JSON response.
    Returns list of {"property_data": ..., "auction_data": ...} dicts.
    """
    body = data.get("body", {})
    records: list[dict] = []

    for item in body.get("content", []):
        try:
            record = _parse_item(item)
            if record:
                records.append(record)
        except Exception as exc:
            log.warning("parser.item_parse_error", error=str(exc), item_id=item.get("id"))

    log.info("parser.page_parsed", count=len(records), total=body.get("totalElements"))
    return records


def is_last_page(data: dict) -> bool:
    return bool(data.get("body", {}).get("last", True))


def _parse_item(item: dict) -> Optional[dict]:
    external_id = str(item.get("id") or "")
    if not external_id:
        return None

    ind = item.get("indirizzo") or {}
    coord = ind.get("coordinate") or {}

    via = (ind.get("via") or "").strip()
    civico = (ind.get("numeroCivico") or "").strip()
    address = f"{via} {civico}".strip() or None

    desc = item.get("descLotto")

    property_data: dict = {
        "external_id": external_id,
        "source": "pvp",
        "address": address,
        "city": ind.get("citta"),
        "province": _province_code(ind.get("provincia")),
        "postal_code": ind.get("cap"),
        "latitude": _to_decimal(coord.get("latitudine")),
        "longitude": _to_decimal(coord.get("longitudine")),
        "property_type": _property_type(item.get("categoriaBene") or []),
        "area_sqm": _extract_sqm(desc),
        "description": desc,
        "encumbrances": _detect_encumbrances(desc),
    }

    auction_data: dict = {
        "external_id": external_id,
        "source": "pvp",
        "court": item.get("tribunale"),
        "court_code": item.get("codiceTribunale"),
        "procedure_number": item.get("procedura"),
        "auction_type": "asincrona_telematica",
        "status": _ESITO_TO_STATUS.get(item.get("esito"), "scheduled"),
        "base_price": _to_decimal(item.get("prezzoBaseAsta")),
        "minimum_bid": _to_decimal(item.get("offertaMinima")),
        "bid_increment": _to_decimal(item.get("rialzoMinimo")),
        "auction_date": _parse_datetime(item.get("dataOraVendita")),
        "publication_date": _parse_datetime(item.get("dataPubblicazione")),
    }

    return {"property_data": property_data, "auction_data": auction_data}
