"""Public-body sale notices: parsing of real Gazzetta Ufficiale texts and edge cases."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.ingestion.public_sales.fixtures import GENZANO_BODY, MOMO_BODY
from app.ingestion.public_sales.notice_parser import (
    classify,
    extract_address,
    extract_price,
    is_real_estate_sale,
    parse_notice,
)

TZ = ZoneInfo("Europe/Rome")


def _genzano(now=datetime(2026, 8, 1, tzinfo=TZ)):
    return parse_notice(
        notice_id="TX26BIA353", source="gu",
        title="Asta pubblica per l'alienazione di immobili di proprieta' comunale",
        body=GENZANO_BODY, ente="COMUNE DI GENZANO DI ROMA",
        sede="via Italo Belardi, 81 - 00045 Genzano di Roma (RM), Italia",
        published=datetime(2026, 7, 27, tzinfo=TZ), now=now,
    )


def _momo(now=datetime(2026, 7, 10, tzinfo=TZ)):
    return parse_notice(
        notice_id="TX26BIA326", source="gu", title="Asta pubblica - Vendita immobiliare",
        body=MOMO_BODY, ente="COMUNE DI MOMO", sede="via Squarini n. 2 - 28015 Momo",
        published=datetime(2026, 7, 8, tzinfo=TZ), now=now,
    )


class TestGenzanoMultiLot:
    def test_one_record_per_lot_with_own_price(self):
        records = _genzano()
        assert [r["auction_data"]["external_id"] for r in records] == [
            f"TX26BIA353-{i}" for i in range(1, 9)
        ]
        prices = [r["auction_data"]["base_price"] for r in records]
        assert prices[0] == Decimal("80000.00")
        assert prices[1] == Decimal("58750.20")
        assert prices[-1] == Decimal("5600.00")

    def test_location_from_selling_comune(self):
        prop = _genzano()[0]["property_data"]
        assert (prop["city"], prop["province"], prop["region"]) == ("Genzano di Roma", "RM", "Lazio")

    def test_dates_ignore_old_law_references(self):
        a = _genzano()[0]["auction_data"]
        # "R.D. 23 maggio 1924" must not be taken as the auction date
        assert a["auction_date"] == datetime(2026, 9, 4, 10, 0, tzinfo=TZ)
        assert a["auction_deadline"] == datetime(2026, 9, 2, 12, 0, tzinfo=TZ)
        assert a["status"] == "scheduled"

    def test_lot_types_and_addresses(self):
        records = _genzano()
        assert records[0]["property_data"]["property_type"] == "commercial"
        assert records[0]["property_data"]["address"] == "Via Luigi Longo 8"
        assert records[1]["property_data"]["address"] == "Largo Dott. Nicola Ottavio snc"
        assert records[-1]["property_data"]["property_type"] == "land"

    def test_seller_and_link_kept(self):
        r = _genzano()[0]
        assert r["auction_data"]["court"] == "COMUNE DI GENZANO DI ROMA"
        assert r["auction_data"]["procedure_number"] == "TX26BIA353"
        assert r["property_data"]["extra"]["lot"] == "1"

    def test_past_auction_marked_completed(self):
        records = _genzano(now=datetime(2026, 10, 1, tzinfo=TZ))
        assert {r["auction_data"]["status"] for r in records} == {"completed"}


class TestMomoSingleLot:
    def test_single_record(self):
        records = _momo()
        assert len(records) == 1
        p, a = records[0]["property_data"], records[0]["auction_data"]
        assert a["external_id"] == "TX26BIA326"
        assert a["base_price"] == Decimal("92750.00")
        assert (p["city"], p["province"]) == ("Momo", "NO")
        assert p["property_type"] == "land"

    def test_auction_time_and_deadline(self):
        a = _momo()[0]["auction_data"]
        assert a["auction_date"] == datetime(2026, 8, 4, 9, 0, tzinfo=TZ)
        assert a["auction_deadline"] == datetime(2026, 8, 3, 12, 0, tzinfo=TZ)

    def test_seat_address_not_taken_as_property_address(self):
        assert _momo()[0]["property_data"]["address"] is None


class TestRelevance:
    def test_lease_is_not_a_sale(self):
        assert not is_real_estate_sale(
            "Avviso di procedura comparativa per la concessione in uso centro sportivo",
            "concessione amministrativa dell'immobile comunale",
        )

    def test_result_notice_is_not_a_sale(self):
        assert not is_real_estate_sale("Esito di gara", "esito della vendita del lotto 1")

    def test_services_tender_is_not_a_sale(self):
        assert not is_real_estate_sale("Bando di gara - Servizi di pulizia", "affidamento servizi")

    def test_sale_of_land(self):
        assert is_real_estate_sale("Asta pubblica - Vendita area comunale", "area edificabile")


class TestFieldExtractors:
    def test_price_after_amount_demanio_style(self):
        assert extract_price("LOTTO N. 3 Prezzo base: 2.625,00 € Euro DUEMILA…") == Decimal("2625.00")

    def test_price_base_d_asta(self):
        assert extract_price("prezzo a base d'asta di euro 98.000,00") == Decimal("98000.00")

    def test_location_in_other_city(self):
        """Comune di Varallo selling a flat it owns in Milano."""
        body = ("Si rende noto che il giorno 13 maggio 2026 alle ore 10:00 avrà luogo un'asta "
                "pubblica per la vendita del seguente immobile: Unità immobiliare sita in "
                "Milano, Via Polesine n. 33, posta al secondo piano con ascensore. "
                "Prezzo a base d'asta € 180.000,00.")
        [r] = parse_notice(
            notice_id="X1", source="gu", title="Avviso di asta pubblica per l'alienazione di bene immobile comunale",
            body=body, ente="COMUNE DI VARALLO", sede="Corso Roma 31 - 13019 Varallo",
            published=datetime(2026, 4, 23, tzinfo=TZ), now=datetime(2026, 4, 24, tzinfo=TZ),
        )
        p = r["property_data"]
        assert (p["city"], p["province"]) == ("Milano", "MI")
        assert p["address"] == "Via Polesine 33"
        assert p["property_type"] == "apartment"
        assert r["auction_data"]["auction_date"] == datetime(2026, 5, 13, 10, 0, tzinfo=TZ)

    def test_classify(self):
        assert classify("capannone artigianale") == "industrial"
        assert classify("box auto interrato") == "garage"
        assert classify("villino con giardino") == "villa"

    def test_address_none_when_absent(self):
        assert extract_address("terreno agricolo foglio 3 mappale 12") is None
