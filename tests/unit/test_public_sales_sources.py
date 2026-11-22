"""Gazzetta Ufficiale / HTML sources: page parsing and resume (cursor) logic."""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.ingestion.public_sales.sources import (
    GazzettaS5Source,
    GuIssue,
    HtmlListSource,
    SourceProgress,
    parse_issue_list,
    parse_issue_summary,
    parse_notice_page,
)

LIST_HTML = """
<a href="https://www.gazzettaufficiale.it/gazzetta/contratti/caricaDettaglio?dataPubblicazioneGazzetta=2026-11-18&numeroGazzetta=132&elenco30giorni=true">n° 132 del 18-11-2026</a>
<a href="https://www.gazzettaufficiale.it/do/gazzetta/downloadPdf?dataPubblicazioneGazzetta=20261118&numeroGazzetta=132">PDF</a>
<a href="https://www.gazzettaufficiale.it/gazzetta/contratti/caricaDettaglio?dataPubblicazioneGazzetta=2026-11-20&numeroGazzetta=133&elenco30giorni=true">n° 133 del 20-11-2026</a>
"""


def summary_html(*codes: str) -> str:
    rows = []
    for code in codes:
        href = ("https://www.gazzettaufficiale.it/atto/contratti/caricaDettaglioAtto/originario?"
                f"atto.dataPubblicazioneGazzetta=2026-11-20&atto.codiceRedazionale={code}")
        rows.append(f'<a href="{href}">COMUNE DI MOMO</a> '
                    f'<a href="{href}">Asta pubblica - Vendita immobiliare ({code}) Pag. 3</a>')
    other = ("https://www.gazzettaufficiale.it/atto/contratti/caricaDettaglioAtto/originario?"
             "atto.dataPubblicazioneGazzetta=2026-11-20&atto.codiceRedazionale=TX26BGA352")
    return f'<a href="{other}">Esito di gara (TX26BGA352) Pag. 1</a>' + "".join(rows)


NOTICE_HTML = """<html><body>
<h2>COMUNE DI MOMO Sede: via Squarini n. 2 - 28015 Momo Partita IVA: 00265210039</h2>
<h3>(GU 5a Serie Speciale - Contratti Pubblici n.77 del 8-7-2026)</h3>
<pre> Asta pubblica - Vendita immobiliare
 prezzo base d'asta di € 92.750,00 per l'alienazione di un terreno.
TX26BIA326</pre></body></html>"""


def test_issue_list_sorted_and_deduplicated():
    issues = parse_issue_list(LIST_HTML)
    assert issues == [GuIssue(date(2026, 11, 18), 132), GuIssue(date(2026, 11, 20), 133)]


def test_issue_summary_keeps_only_real_estate_section():
    entries = parse_issue_summary(summary_html("TX26BIA326"))
    assert entries == [("TX26BIA326", "Asta pubblica - Vendita immobiliare")]


def test_notice_page_split_into_ente_sede_body():
    ente, sede, body = parse_notice_page(NOTICE_HTML)
    assert ente == "COMUNE DI MOMO"
    assert sede == "via Squarini n. 2 - 28015 Momo"
    assert "92.750,00" in body and "Sede" not in body


class FakeClient:
    """Serves canned pages by URL; records what was requested."""

    def __init__(self, pages: dict[str, str], fail: set[str] = frozenset()):
        self.pages, self.fail, self.calls = pages, fail, []

    async def get(self, url, params=None, **_):
        self.calls.append(url)
        status = 500 if url in self.fail else (200 if url in self.pages else 404)
        return httpx.Response(status, text=self.pages.get(url, ""), request=httpx.Request("GET", url))


def _site(src: GazzettaS5Source, fail_notice: str | None = None):
    i132, i133 = GuIssue(date(2026, 11, 18), 132), GuIssue(date(2026, 11, 20), 133)
    pages = {
        f"{src.BASE}/30giorni/contratti": LIST_HTML,
        src.issue_url(i132): summary_html("TX26BIA500"),
        src.issue_url(i133): summary_html("TX26BIA326", "TX26BIA327"),
        src.notice_url(i132, "TX26BIA500"): NOTICE_HTML,
        src.notice_url(i133, "TX26BIA326"): NOTICE_HTML,
        src.notice_url(i133, "TX26BIA327"): NOTICE_HTML,
    }
    fail = {src.notice_url(i133, fail_notice)} if fail_notice else set()
    return FakeClient(pages, fail)


async def _collect(src, client, cursor=None, known=frozenset()):
    progress = SourceProgress()
    notices = [n async for n in src.fetch(client, cursor, set(known), progress)]
    return notices, progress


class TestGazzettaFetch:
    async def test_first_run_reads_all_issues_and_advances_cursor(self):
        src = GazzettaS5Source({})
        notices, progress = await _collect(src, _site(src))
        assert [n.notice_id for n in notices] == ["TX26BIA500", "TX26BIA326", "TX26BIA327"]
        assert progress.cursor == "2026-11-20"
        assert notices[0].ente == "COMUNE DI MOMO"
        assert notices[0].published.date() == date(2026, 11, 18)

    async def test_cursor_skips_processed_issues(self):
        src = GazzettaS5Source({})
        client = _site(src)
        notices, _ = await _collect(src, client, cursor="2026-11-18")
        assert [n.notice_id for n in notices] == ["TX26BIA326", "TX26BIA327"]
        assert src.issue_url(GuIssue(date(2026, 11, 18), 132)) not in client.calls

    async def test_known_notices_are_not_fetched_again(self):
        src = GazzettaS5Source({})
        client = _site(src)
        notices, progress = await _collect(src, client, known={"TX26BIA326", "TX26BIA500"})
        assert [n.notice_id for n in notices] == ["TX26BIA327"]
        assert progress.skipped_known == 2

    async def test_failed_notice_keeps_cursor_on_previous_issue(self):
        src = GazzettaS5Source({})
        notices, progress = await _collect(src, _site(src, fail_notice="TX26BIA327"))
        assert progress.errors == 1
        assert progress.cursor == "2026-11-18"   # issue 133 will be retried next run
        assert "TX26BIA326" in [n.notice_id for n in notices]


class TestHtmlListSource:
    def test_links_filtered_by_include_exclude(self):
        src = HtmlListSource({
            "name": "comune_x", "list_url": "https://comune.x.it/bandi/",
            "seller": "Comune di X",
        })
        html = """
          <a href="/bandi/asta-alienazione-immobile-via-roma.html">Asta pubblica alienazione immobile via Roma</a>
          <a href="/bandi/locazione-negozio.html">Avviso locazione negozio</a>
          <a href="/bandi/esito-asta.pdf">Esito asta pubblica vendita</a>
          <a href="/bandi/vendita-terreno.pdf">Vendita terreno comunale</a>"""
        links = src.candidate_links(html)
        assert links == [
            ("https://comune.x.it/bandi/asta-alienazione-immobile-via-roma.html",
             "Asta pubblica alienazione immobile via Roma"),
            ("https://comune.x.it/bandi/vendita-terreno.pdf", "Vendita terreno comunale"),
        ]

    def test_stable_notice_ids(self):
        src = HtmlListSource({"name": "c", "list_url": "https://c.it/"})
        assert src.notice_id("https://c.it/a") == src.notice_id("https://c.it/a")
        assert src.notice_id("https://c.it/a") != src.notice_id("https://c.it/b")


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("real network call")
    monkeypatch.setattr(httpx.AsyncClient, "request", _boom)
