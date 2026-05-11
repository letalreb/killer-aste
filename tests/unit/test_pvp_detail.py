"""Unit tests for pvp_detail parsers (no network calls)."""
from decimal import Decimal

import pytest

from app.ingestion.pvp_detail import _parse_json_detail, _parse_html_detail


# ── JSON detail parser ────────────────────────────────────────────────────────

def _out() -> dict:
    return {
        "market_value": None,
        "source_url": "https://example.com",
        "expert_report_url": None,
        "deposit_required": None,
        "auction_deadline": None,
    }


class TestParseJsonDetail:
    def test_extracts_valore_stima(self):
        data = {"body": {"valoreStima": 120000.0}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["market_value"] == Decimal("120000.0")

    def test_extracts_valore_perizia(self):
        data = {"body": {"valorePerizia": "95000"}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["market_value"] == Decimal("95000")

    def test_ignores_zero_market_value(self):
        data = {"body": {"valoreStima": 0}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["market_value"] is None

    def test_extracts_perizia_url(self):
        data = {"body": {"urlPerizia": "https://pvp.giustizia.it/perizia/123.pdf"}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["expert_report_url"] == "https://pvp.giustizia.it/perizia/123.pdf"

    def test_extracts_deposit(self):
        data = {"body": {"prezzoDeposito": 5000.0}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["deposit_required"] == Decimal("5000.0")

    def test_extracts_deadline(self):
        data = {"body": {"dataScadenzaOfferta": "2025-06-15T12:00:00"}}
        out = _out()
        _parse_json_detail(data, out)
        assert out["auction_deadline"] is not None
        assert out["auction_deadline"].year == 2025

    def test_tolerates_missing_body_wrapper(self):
        # Some endpoints return the object directly without {"body": ...}
        data = {"valoreStima": 80000}
        out = _out()
        _parse_json_detail(data, out)
        assert out["market_value"] == Decimal("80000")

    def test_tolerates_empty_body(self):
        out = _out()
        _parse_json_detail({}, out)
        assert out["market_value"] is None


# ── HTML detail parser ────────────────────────────────────────────────────────

_HTML_DL = """
<html><body>
  <dl>
    <dt>Valore di stima</dt><dd>€ 150.000,00</dd>
    <dt>Cauzione</dt><dd>€ 15.000,00</dd>
    <dt>Scadenza offerte</dt><dd>15/06/2025 12:00</dd>
  </dl>
  <a href="/pvp/docs/perizia_123.pdf">Perizia tecnica</a>
</body></html>
"""

_HTML_TABLE = """
<html><body>
  <table>
    <tr><th>Valore di stima</th><td>120.000,50 €</td></tr>
    <tr><th>Deposito cauzionale</th><td>12.000,00 €</td></tr>
  </table>
</body></html>
"""


class TestParseHtmlDetail:
    def test_extracts_from_dl(self):
        out = _out()
        _parse_html_detail(_HTML_DL, out)
        assert out["market_value"] == Decimal("150000.00")
        assert out["deposit_required"] == Decimal("15000.00")
        assert out["auction_deadline"] is not None

    def test_extracts_expert_link_from_dl(self):
        out = _out()
        _parse_html_detail(_HTML_DL, out)
        assert out["expert_report_url"] == "https://pvp.giustizia.it/pvp/docs/perizia_123.pdf"

    def test_extracts_from_table(self):
        out = _out()
        _parse_html_detail(_HTML_TABLE, out)
        assert out["market_value"] == Decimal("120000.50")
        assert out["deposit_required"] == Decimal("12000.00")

    def test_tolerates_empty_html(self):
        out = _out()
        _parse_html_detail("<html></html>", out)
        assert out["market_value"] is None

    def test_does_not_overwrite_existing_value(self):
        out = _out()
        out["market_value"] = Decimal("99999")
        _parse_html_detail(_HTML_DL, out)
        assert out["market_value"] == Decimal("99999")  # unchanged
