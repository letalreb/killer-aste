"""
PVP detail-page fetcher.

For each auction we scrape two things from PVP:

1. valoreStima  — the court-appointed expert's appraisal value.
   Tried in order:
     a) JSON REST endpoint: GET /ric-…/ric-ms/dettaglio/{id}?language=it
     b) HTML page:          GET /pvp/it/detail_offerta.page?idOfferta={id}
        parsed with BeautifulSoup/lxml.
   The JSON path is tried first; if it 404s or returns no useful body we
   fall back to HTML scraping.

2. source_url  — the canonical public URL where a bidder can participate:
   https://pvp.giustizia.it/pvp/it/detail_offerta.page?idOfferta={id}
   This is constructed deterministically without a network call.

3. expert_report_url (best-effort) — URL to the PDF perizia, if found in
   the detail JSON or HTML.

Return value: dict with keys
  market_value        Optional[Decimal]
  source_url          str
  expert_report_url   Optional[str]
  deposit_required    Optional[Decimal]
  auction_deadline    Optional[datetime]
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog
from bs4 import BeautifulSoup

from app.ingestion.http_client import AntiBanHTTPClient

log = structlog.get_logger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

_MONEY_RE = re.compile(r"[\d.,]+")


def _parse_money(raw: object) -> Optional[Decimal]:
    """Parse an Italian money string or number into Decimal."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None
    text = str(raw).strip()
    # Remove currency symbols and spaces, then normalise Italian decimal style
    text = text.replace("€", "").replace(" ", "").replace("\xa0", "")
    # If there are dots as thousands separators and comma as decimal:
    #   "120.000,50" → "120000.50"
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    m = _MONEY_RE.search(text)
    if not m:
        return None
    try:
        return Decimal(m.group())
    except InvalidOperation:
        return None


def _parse_date(raw: object) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# ── Main public function ──────────────────────────────────────────────────────

async def fetch_detail(
    client: AntiBanHTTPClient,
    base_url: str,
    external_id: str,
    *,
    detail_api_path: str = "/ric-496b258c-986a1b71/ric-ms/offerta/{id}",
    detail_html_path: str = "/pvp/it/detail_offerta.page",
    stats: dict | None = None,
) -> dict:
    """
    Fetch detail data for one auction.

    Always returns a dict (never raises).  Missing fields are None.
    Increments stats["requests_made"] for every HTTP call attempted.
    """
    source_url = f"{base_url}{detail_html_path}?idOfferta={external_id}"
    result: dict = {
        "market_value": None,
        "source_url": source_url,
        "expert_report_url": None,
        "deposit_required": None,
        "auction_deadline": None,
    }

    # ── 1. Try JSON REST detail endpoint ──────────────────────────────────────
    json_path = detail_api_path.format(id=external_id)
    json_url = f"{base_url}{json_path}"
    try:
        resp = await client.get(json_url, params={"language": "it"})
        if stats is not None:
            stats["requests_made"] += 1
        if resp.status_code == 200:
            _parse_json_detail(resp.json(), result)
            log.debug("pvp_detail.json_ok", external_id=external_id)
    except Exception as exc:
        if stats is not None:
            stats["requests_made"] += 1
        log.debug("pvp_detail.json_failed", external_id=external_id, error=str(exc))

    # ── 2. HTML fallback if appraisal still missing ───────────────────────────
    if result["market_value"] is None:
        try:
            resp = await client.get(source_url)
            if stats is not None:
                stats["requests_made"] += 1
            if resp.status_code == 200:
                _parse_html_detail(resp.text, result)
                log.debug("pvp_detail.html_ok", external_id=external_id)
        except Exception as exc:
            if stats is not None:
                stats["requests_made"] += 1
            log.debug("pvp_detail.html_failed", external_id=external_id, error=str(exc))

    if result["market_value"] is not None:
        log.info(
            "pvp_detail.appraisal_found",
            external_id=external_id,
            market_value=float(result["market_value"]),
        )
    else:
        log.debug("pvp_detail.no_appraisal", external_id=external_id)

    return result


# ── JSON parser ───────────────────────────────────────────────────────────────

def _parse_json_detail(data: dict, out: dict) -> None:
    """
    Extract fields from the PVP JSON detail response.

    PVP wraps results in {"messaggio": ..., "body": {...}}.
    Known field names (may vary by API version):
      valoreStima / valorePerito / valoreBase
      urlPerizia  / linkPerizia  / urlDocumentoPerizia
      urlPartecipazione
      prezzoDeposito / cauzione
      dataScadenzaOfferta / dataFineOfferta / dataScadenza
    """
    body = data.get("body") or data  # tolerate missing wrapper

    # ── Appraisal value ───────────────────────────────────────────────────────
    for field in ("valoreStima", "valorePerito", "valorePerizia",
                  "valoreBaseAsta", "valoreStimato"):
        v = body.get(field)
        if v is not None:
            parsed = _parse_money(v)
            if parsed and parsed > 0:
                out["market_value"] = parsed
                break

    # ── Expert report URL ─────────────────────────────────────────────────────
    for field in ("urlPerizia", "linkPerizia", "urlDocumentoPerizia",
                  "urlDocPerizia", "linkDocumentoPerizia"):
        v = body.get(field)
        if v and isinstance(v, str) and v.startswith("http"):
            out["expert_report_url"] = v
            break

    # ── Deposit ───────────────────────────────────────────────────────────────
    for field in ("prezzoDeposito", "cauzione", "depositoCauzionale",
                  "importoDeposito"):
        v = body.get(field)
        if v is not None:
            parsed = _parse_money(v)
            if parsed and parsed > 0:
                out["deposit_required"] = parsed
                break

    # ── Bid deadline ──────────────────────────────────────────────────────────
    for field in ("dataScadenzaOfferta", "dataFineOfferta",
                  "dataScadenza", "dataScadenzaOrdine"):
        v = body.get(field)
        if v:
            parsed_dt = _parse_date(v)
            if parsed_dt:
                out["auction_deadline"] = parsed_dt
                break


# ── HTML parser ───────────────────────────────────────────────────────────────

# Label → canonical key mapping for the HTML detail table
_HTML_LABEL_MAP: dict[str, str] = {
    "valore di stima": "market_value",
    "valore stimato": "market_value",
    "valore perizia": "market_value",
    "valore perito": "market_value",
    "prezzo stimato": "market_value",
    "cauzione": "deposit_required",
    "deposito cauzionale": "deposit_required",
    "scadenza offerte": "auction_deadline",
    "data scadenza": "auction_deadline",
    "scadenza": "auction_deadline",
}

# Text fragments that identify a link to the expert report PDF
_PERIZIA_KEYWORDS = ("perizia", "relazione tecnica", "rapporto di stima", "doc tecnico")


def _parse_html_detail(html: str, out: dict) -> None:
    """Parse the PVP HTML detail page using BeautifulSoup/lxml."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # ── Strategy 1: definition-list / th-td table pairs ──────────────────────
    # Handles both <dl><dt>label</dt><dd>value</dd></dl>
    # and <table><tr><th>label</th><td>value</td></tr></table>
    _extract_label_value_pairs(soup, out)

    # ── Strategy 2: data-label attributes (Bootstrap-style responsive tables)
    for el in soup.find_all(attrs={"data-label": True}):
        label = el.get("data-label", "").strip().lower()
        key = _HTML_LABEL_MAP.get(label)
        if key and out.get(key) is None:
            _set_parsed(key, el.get_text(strip=True), out)

    # ── Expert report link ────────────────────────────────────────────────────
    if out["expert_report_url"] is None:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if any(kw in text or kw in href.lower() for kw in _PERIZIA_KEYWORDS):
                url = href if href.startswith("http") else f"https://pvp.giustizia.it{href}"
                out["expert_report_url"] = url
                break


def _extract_label_value_pairs(soup: BeautifulSoup, out: dict) -> None:
    # dl / dt+dd pairs
    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower().rstrip(":")
        key = _HTML_LABEL_MAP.get(label)
        if not key:
            continue
        dd = dt.find_next_sibling("dd")
        if dd and out.get(key) is None:
            _set_parsed(key, dd.get_text(strip=True), out)

    # th / td pairs (first column label, second column value)
    for th in soup.find_all("th"):
        label = th.get_text(strip=True).lower().rstrip(":")
        key = _HTML_LABEL_MAP.get(label)
        if not key:
            continue
        td = th.find_next_sibling("td")
        if not td:
            # Some tables put th and td in separate cells of the same <tr>
            tr = th.find_parent("tr")
            if tr:
                tds = tr.find_all("td")
                td = tds[0] if tds else None
        if td and out.get(key) is None:
            _set_parsed(key, td.get_text(strip=True), out)

    # span/div with class patterns like "label" + sibling "value"
    for el in soup.find_all(["span", "div", "p"],
                             class_=re.compile(r"label|caption|header", re.I)):
        label = el.get_text(strip=True).lower().rstrip(":")
        key = _HTML_LABEL_MAP.get(label)
        if not key:
            continue
        sibling = el.find_next_sibling()
        if sibling and out.get(key) is None:
            _set_parsed(key, sibling.get_text(strip=True), out)


def _set_parsed(key: str, raw_text: str, out: dict) -> None:
    if key in ("market_value", "deposit_required"):
        v = _parse_money(raw_text)
        if v and v > 0:
            out[key] = v
    elif key == "auction_deadline":
        v = _parse_date(raw_text)
        if v:
            out[key] = v
