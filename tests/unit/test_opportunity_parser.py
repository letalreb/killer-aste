"""Unit tests for app.ingestion.discovery.opportunity_parser."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.ingestion.discovery.opportunity_parser import (
    _classify_type,
    _extract_budget_text,
    _extract_province_from_text,
    parse_opportunity,
)


class TestClassifyType:
    def test_rigenerazione_urbana(self):
        assert _classify_type("piano di rigenerazione urbana del quartiere") == "rigenerazione_urbana"

    def test_pnrr(self):
        assert _classify_type("progetto pnrr misura m2 digitalizzazione") == "pnrr_progetto"

    def test_alienazione_pubblica(self):
        assert _classify_type("bando di alienazione immobile comunale") == "alienazione_pubblica"

    def test_investimento_infrastrutturale(self):
        assert _classify_type("nuovo asse viario infrastruttura urbana") == "investimento_infrastrutturale"

    def test_piano_urbanistico(self):
        assert _classify_type("variante al piano regolatore generale prg") == "piano_urbanistico"

    def test_unknown_returns_altro(self):
        assert _classify_type("testo generico senza parole chiave") == "altro"

    def test_prefers_strongest_signal(self):
        # rigenerazione_urbana has more keywords than altro
        text = "rigenerazione urbana e riqualificazione del quartiere pnrr"
        result = _classify_type(text)
        assert result in ("rigenerazione_urbana", "pnrr_progetto")


class TestExtractBudgetText:
    def test_italian_format(self):
        result = _extract_budget_text("importo totale: € 2.500.000,00")
        assert result == Decimal("2500000.00")

    def test_plain_euro(self):
        result = _extract_budget_text("costo euro 750.000,00")
        assert result == Decimal("750000.00")

    def test_too_small_ignored(self):
        result = _extract_budget_text("costo € 50,00")
        assert result is None  # below the 1000 threshold

    def test_no_budget(self):
        assert _extract_budget_text("nessun importo nel testo") is None


class TestExtractProvince:
    def test_known_province_code(self):
        result = _extract_province_from_text("Intervento nel Comune di Bologna BO")
        assert result == "BO"

    def test_unknown_code_returns_none(self):
        result = _extract_province_from_text("testo senza codice provincia")
        assert result is None

    def test_rome(self):
        result = _extract_province_from_text("Progetto a Roma RM")
        assert result == "RM"


class TestParseOpportunity:
    def test_parse_dict_returns_structured(self):
        raw = {
            "titolo": "Piano di rigenerazione del quartiere San Vitale",
            "descrizione": "Intervento di riqualificazione urbana nel quartiere BO",
            "provincia": "BO",
            "comune": "Bologna",
            "importo": "5000000",
            "link": "https://www.comune.bologna.it/piano-rigenerazione",
        }
        result = parse_opportunity(raw, source="test")
        assert result is not None
        assert result["title"] == "Piano di rigenerazione del quartiere San Vitale"
        assert result["opportunity_type"] == "rigenerazione_urbana"
        assert result["province"] == "BO"
        assert result["city"] == "Bologna"
        assert result["source"] == "test"

    def test_parse_dict_no_title_returns_none(self):
        result = parse_opportunity({"descrizione": "qualcosa"}, source="test")
        assert result is None

    def test_parse_text_classifiable(self):
        text = (
            "Piano di rigenerazione urbana del quartiere industriale dismesso. "
            "Importo totale: € 3.200.000,00. Anno completamento: 2027. "
            "Comune di Milano MI."
        )
        result = parse_opportunity(text, source="text_test")
        assert result is not None
        assert result["opportunity_type"] == "rigenerazione_urbana"
        assert result["province"] == "MI"
        assert result["budget_amount"] == Decimal("3200000.00")
        assert result["expected_completion"] == "2027"

    def test_parse_text_too_short_returns_none(self):
        assert parse_opportunity("ok", source="x") is None

    def test_parse_text_unclassifiable_short_returns_none(self):
        assert parse_opportunity("testo breve senza senso", source="x") is None

    def test_budget_url_stored_in_source_url(self):
        raw = {
            "name": "Alienazione immobile via Roma",
            "url": "https://example.com/alienazione",
        }
        result = parse_opportunity(raw, source="test")
        assert result is not None
        assert result["source_url"] == "https://example.com/alienazione"

    def test_invalid_type_returns_dict(self):
        raw = {"title": "Progetto PNRR digitalizzazione PA", "province": "MI"}
        result = parse_opportunity(raw, source="test")
        assert result is not None
        assert result["opportunity_type"] == "pnrr_progetto"
