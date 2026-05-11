"""
Dry-run mock responses — JSON format matching the real PVP REST API.

Endpoint: POST /ric-496b258c-986a1b71/ric-ms/ricerca/vendite
Response shape: {"messaggio": "...", "body": {Spring Page object}}
"""
from __future__ import annotations

import json
import math

import httpx

_LOTTO_UNICO = "LOTTO UNICO"

_MOCK_RECORDS = [
    {
        "id": 1001,
        "tipoLotto": "IMMOBILI",
        "categoriaLotto": "IMMOBILE_RESIDENZIALE",
        "categoriaBene": ["ABITAZIONE_TIPO_A"],
        "indirizzo": {
            "via": "Via Roma, 15",
            "numeroCivico": "",
            "cap": "20100",
            "citta": "Milano",
            "provincia": "Milano",
            "coordinate": {"latitudine": 45.4654, "longitudine": 9.1859},
        },
        "numeroLotto": _LOTTO_UNICO,
        "procedura": "1234/2023",
        "prezzoBaseAsta": 180000.0,
        "offertaMinima": 135000.0,
        "rialzoMinimo": 1800.0,
        "dataOraVendita": "2024-03-15T10:00",
        "dataPubblicazione": "2024-01-10",
        "descLotto": "Appartamento 3 locali con ipoteca. 85 mq al terzo piano.",
        "tribunale": "Tribunale di Milano",
        "codiceTribunale": "0288040091",
        "esito": None,
    },
    {
        "id": 1002,
        "tipoLotto": "IMMOBILI",
        "categoriaLotto": "IMMOBILE_RESIDENZIALE",
        "categoriaBene": ["VILLA"],
        "indirizzo": {
            "via": "Via Appia, 8",
            "numeroCivico": "",
            "cap": "00179",
            "citta": "Roma",
            "provincia": "Roma",
            "coordinate": {"latitudine": 41.8902, "longitudine": 12.4922},
        },
        "numeroLotto": _LOTTO_UNICO,
        "procedura": "5678/2023",
        "prezzoBaseAsta": 450000.0,
        "offertaMinima": 337500.0,
        "rialzoMinimo": 4500.0,
        "dataOraVendita": "2024-03-22T14:30",
        "dataPubblicazione": "2024-01-15",
        "descLotto": "Villa con giardino, pignoramento in corso. 220 mq.",
        "tribunale": "Tribunale di Roma",
        "codiceTribunale": "0587040091",
        "esito": None,
    },
    {
        "id": 1003,
        "tipoLotto": "IMMOBILI",
        "categoriaLotto": "IMMOBILE_COMMERCIALE",
        "categoriaBene": ["NEGOZIO"],
        "indirizzo": {
            "via": "Corso Vittorio Emanuele, 100",
            "numeroCivico": "",
            "cap": "10121",
            "citta": "Torino",
            "provincia": "Torino",
            "coordinate": {"latitudine": 45.0703, "longitudine": 7.6869},
        },
        "numeroLotto": _LOTTO_UNICO,
        "procedura": "9012/2023",
        "prezzoBaseAsta": 95000.0,
        "offertaMinima": 71250.0,
        "rialzoMinimo": 950.0,
        "dataOraVendita": "2024-04-05T09:00",
        "dataPubblicazione": "2024-01-20",
        "descLotto": "Locale commerciale 120 mq, piano terra.",
        "tribunale": "Tribunale di Torino",
        "codiceTribunale": "0900140091",
        "esito": None,
    },
]


def _make_page_response(page: int, size: int = 10) -> httpx.Response:
    total = len(_MOCK_RECORDS)
    total_pages = max(1, math.ceil(total / size))
    start = page * size
    content = _MOCK_RECORDS[start: start + size]
    body = {
        "content": content,
        "totalElements": total,
        "totalPages": total_pages,
        "size": size,
        "number": page,
        "last": page >= total_pages - 1,
        "first": page == 0,
        "numberOfElements": len(content),
        "empty": len(content) == 0,
    }
    payload = {"messaggio": "Operazione effettuata con successo", "body": body}
    return httpx.Response(
        status_code=200,
        headers={"content-type": "application/json"},
        content=json.dumps(payload).encode(),
    )


def get_mock_response(params: dict | None = None, **_: object) -> httpx.Response:
    page = int((params or {}).get("page", 0))
    return _make_page_response(page=page)
