"""Unit tests for the PVP JSON REST API parser."""
from __future__ import annotations

import pytest
from app.ingestion.parser import is_last_page, parse_api_response
from app.ingestion.mock_responses import _make_page_response, _MOCK_RECORDS


def _page(records: list, page: int = 0, total: int | None = None, last: bool = False) -> dict:
    t = total if total is not None else len(records)
    return {
        "messaggio": "Operazione effettuata con successo",
        "body": {
            "content": records,
            "totalElements": t,
            "totalPages": max(1, (t + 9) // 10),
            "size": 10,
            "number": page,
            "last": last,
            "first": page == 0,
            "numberOfElements": len(records),
            "empty": len(records) == 0,
        },
    }


class TestParseApiResponse:
    def test_parses_all_mock_records(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        assert len(records) == len(_MOCK_RECORDS)

    def test_property_fields_present(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        prop = records[0]["property_data"]
        assert prop["external_id"] == "1001"
        assert prop["city"] == "Milano"
        assert prop["province"] == "MI"
        assert prop["property_type"] == "apartment"
        assert prop["source"] == "pvp"

    def test_auction_fields_present(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        auction = records[0]["auction_data"]
        assert float(auction["base_price"]) == 180_000.0
        assert float(auction["minimum_bid"]) == 135_000.0
        assert auction["court"] == "Tribunale di Milano"
        assert auction["auction_type"] == "asincrona_telematica"
        assert auction["status"] == "scheduled"

    def test_empty_page_returns_empty_list(self):
        data = _page([], last=True)
        records = parse_api_response(data)
        assert records == []

    def test_property_types_mapped(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        types = {r["property_data"]["property_type"] for r in records}
        assert "apartment" in types
        assert "villa" in types
        assert "commercial" in types

    def test_encumbrances_detected(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        # Record 1001 has "ipoteca" in descLotto
        enc = records[0]["property_data"]["encumbrances"]
        assert enc is not None
        assert "ipoteca" in enc

    def test_coordinates_parsed(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        prop = records[0]["property_data"]
        assert prop["latitude"] is not None
        assert prop["longitude"] is not None

    def test_missing_id_skips_record(self):
        bad = [{"tipoLotto": "IMMOBILI"}]
        data = _page(bad)
        records = parse_api_response(data)
        assert records == []

    def test_province_full_name_mapped_to_code(self):
        record = dict(_MOCK_RECORDS[0])
        record["indirizzo"] = dict(record["indirizzo"])
        record["indirizzo"]["provincia"] = "Roma"
        data = _page([record])
        records = parse_api_response(data)
        assert records[0]["property_data"]["province"] == "RM"

    def test_unknown_province_returns_none(self):
        record = dict(_MOCK_RECORDS[0])
        record["indirizzo"] = dict(record["indirizzo"])
        record["indirizzo"]["provincia"] = "NonEsiste"
        data = _page([record])
        records = parse_api_response(data)
        assert records[0]["property_data"]["province"] is None

    def test_esito_aggiudicato_maps_completed(self):
        record = {**_MOCK_RECORDS[0], "esito": "AGGIUDICATO"}
        data = _page([record])
        records = parse_api_response(data)
        assert records[0]["auction_data"]["status"] == "completed"

    def test_auction_date_parsed(self):
        resp = _make_page_response(page=0).json()
        records = parse_api_response(resp)
        assert records[0]["auction_data"]["auction_date"] is not None

    def test_malformed_date_does_not_raise(self):
        record = {**_MOCK_RECORDS[0], "dataOraVendita": "not-a-date"}
        data = _page([record])
        records = parse_api_response(data)
        assert records[0]["auction_data"]["auction_date"] is None

    def test_parse_error_in_one_item_does_not_stop_others(self):
        records_in = [_MOCK_RECORDS[0], {"id": None}, _MOCK_RECORDS[1]]
        data = _page(records_in)
        records = parse_api_response(data)
        assert len(records) == 2  # middle item skipped (no id)


class TestIsLastPage:
    def test_last_true(self):
        data = _page([], last=True)
        assert is_last_page(data) is True

    def test_last_false(self):
        data = _page(_MOCK_RECORDS, last=False)
        assert is_last_page(data) is False

    def test_missing_body_returns_true(self):
        # Missing body → assume last to avoid infinite loop
        assert is_last_page({}) is True
