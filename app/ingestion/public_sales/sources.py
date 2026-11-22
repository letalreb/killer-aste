"""
Where public-body sale notices come from.

GazzettaS5Source
    Gazzetta Ufficiale, 5a Serie Speciale – Contratti Pubblici, section
    "Aste immobiliari ed altre procedure ad evidenza pubblica". Public bodies
    (Comuni, Province, ASL, Università, Demanio, fondazioni pubbliche…) must
    publish their real-estate auction notices there, so it is the broadest
    single national source. Notices in that section have editorial codes like
    TX26BIA326 ("BIA" = aste immobiliari).

      /30giorni/contratti                       → issues of the last 30 days
      /eli/gu/YYYY/MM/DD/N/s5/html              → issue summary (notice links)
      /atto/contratti/caricaDettaglioAtto/…     → one notice (plain text)

HtmlListSource
    Any ente page that lists sale notices (a Comune's "Bandi e avvisi", a
    Regione or ALER sales page, …): a listing URL, a CSS selector for the
    links, a regex to keep only sale notices, and optionally a CSS selector
    for the notice text. PDF links are read with the existing PDF extractor.
    Configured in config.yaml, so new sources need no code.

Every source yields RawNotice objects; parsing happens in notice_parser.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import AsyncIterator, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import structlog
from bs4 import BeautifulSoup

from app.ingestion.http_client import PoliteHTTPClient

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("Europe/Rome")


@dataclass
class RawNotice:
    notice_id: str
    source: str
    title: str
    body: str
    ente: str
    sede: str = ""
    url: Optional[str] = None
    published: Optional[datetime] = None


@dataclass
class SourceProgress:
    """What a source managed to process, so the next run can resume."""
    cursor: Optional[str] = None          # source-specific (GU: last issue date)
    fetched: int = 0
    skipped_known: int = 0
    errors: int = 0
    notes: list[str] = field(default_factory=list)


# ── Gazzetta Ufficiale 5a serie ───────────────────────────────────────────────

_ISSUE_LINK = re.compile(
    r"caricaDettaglio\?dataPubblicazioneGazzetta=(\d{4})-(\d{2})-(\d{2})&numeroGazzetta=(\d+)"
)
_NOTICE_CODE = re.compile(r"codiceRedazionale=(TX\d{2}BIA\d+)")
_TITLE_TAIL = re.compile(r"\s*\(TX\d{2}[A-Z]{3}\d+\)\s*(?:Pag\.\s*\d+)?\s*$")
_SEDE_END = re.compile(
    r"\b(Punti di contatto|Codice Fiscale|Partita IVA|E-?mail|Tel\.|PEC|Registro delle imprese)\b",
    re.I,
)


@dataclass(frozen=True)
class GuIssue:
    day: date
    number: int

    @property
    def key(self) -> str:
        return f"{self.day.isoformat()}/{self.number}"


def parse_issue_list(html: str) -> list[GuIssue]:
    issues = {
        GuIssue(date(int(y), int(m), int(d)), int(n))
        for y, m, d, n in _ISSUE_LINK.findall(html)
    }
    return sorted(issues, key=lambda i: (i.day, i.number))


def parse_issue_summary(html: str) -> list[tuple[str, str]]:
    """[(notice code, title)] for the real-estate auction section of one issue."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = _NOTICE_CODE.search(a["href"])
        if not m:
            continue
        text = a.get_text(" ", strip=True)
        # Each notice has two links: the body name, then the title "(TX…) Pag. N".
        if "(TX" in text or m.group(1) not in found:
            found[m.group(1)] = _TITLE_TAIL.sub("", text)
    return list(found.items())


def parse_notice_page(html: str) -> tuple[str, str, str]:
    """(ente, sede, body text) from a GU notice page."""
    soup = BeautifulSoup(html, "lxml")
    header = soup.find("h2")
    header_text = header.get_text(" ", strip=True) if header else ""
    ente, _, rest = header_text.partition("Sede:")
    sede = _SEDE_END.split(rest, maxsplit=1)[0].strip(" ,;") if rest else ""
    pre = soup.find("pre")
    body = pre.get_text("\n") if pre else soup.get_text("\n")
    return ente.strip(), sede, body


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return re.sub(r"\s+", " ", line).strip()
    return ""


class GazzettaS5Source:
    name = "gu"
    BASE = "https://www.gazzettaufficiale.it"

    def __init__(self, cfg: dict) -> None:
        self._max_issues = int(cfg.get("max_issues_per_run", 15))

    def issue_url(self, issue: GuIssue) -> str:
        d = issue.day
        return f"{self.BASE}/eli/gu/{d:%Y/%m/%d}/{issue.number}/s5/html"

    def notice_url(self, issue: GuIssue, code: str) -> str:
        return (
            f"{self.BASE}/atto/contratti/caricaDettaglioAtto/originario?"
            f"atto.dataPubblicazioneGazzetta={issue.day.isoformat()}"
            f"&atto.codiceRedazionale={code}"
        )

    async def fetch(
        self,
        client: PoliteHTTPClient,
        cursor: Optional[str],
        known_ids: set[str],
        progress: SourceProgress,
    ) -> AsyncIterator[RawNotice]:
        """
        Yield notices from issues published after ``cursor`` (an ISO date).
        Notices whose code is in ``known_ids`` are not fetched again.
        The cursor only advances past issues that were processed without errors.
        """
        listing = await client.get(f"{self.BASE}/30giorni/contratti")
        listing.raise_for_status()
        issues = parse_issue_list(listing.text)
        if cursor:
            issues = [i for i in issues if i.day.isoformat() > cursor]
        issues = issues[: self._max_issues]
        progress.cursor = cursor

        for issue in issues:
            issue_ok = True
            try:
                resp = await client.get(self.issue_url(issue))
                resp.raise_for_status()
                entries = parse_issue_summary(resp.text)
            except Exception as exc:
                log.warning("public_sales.gu_issue_error", issue=issue.key, error=str(exc))
                progress.errors += 1
                break  # keep the cursor here; retry this issue next run

            for code, title in entries:
                if code in known_ids:
                    progress.skipped_known += 1
                    continue
                url = self.notice_url(issue, code)
                try:
                    page = await client.get(url)
                    page.raise_for_status()
                    ente, sede, body = parse_notice_page(page.text)
                except Exception as exc:
                    log.warning("public_sales.gu_notice_error", code=code, error=str(exc))
                    progress.errors += 1
                    issue_ok = False
                    continue
                progress.fetched += 1
                yield RawNotice(
                    notice_id=code,
                    source=self.name,
                    title=title or first_line(body),
                    body=body,
                    ente=ente,
                    sede=sede,
                    url=url,
                    published=datetime(issue.day.year, issue.day.month, issue.day.day, tzinfo=_TZ),
                )
            if not issue_ok:
                break
            progress.cursor = issue.day.isoformat()


# ── Generic HTML listing ──────────────────────────────────────────────────────

class HtmlListSource:
    """
    Config example (config.yaml → public_sales.html_sources):

      - name: comune_milano_alienazioni
        enabled: true
        list_url: https://www.comune.example.it/bandi-e-avvisi
        link_selector: "a"                 # CSS selector for candidate links
        include: "(alienazion|vendita|asta pubblica)"   # regex on link text/href
        exclude: "(esito|locazion|concession)"
        text_selector: "main"              # CSS selector for the notice body (HTML pages)
        seller: "Comune di Milano"
        max_items: 20
    """

    def __init__(self, cfg: dict) -> None:
        self.name = cfg["name"]
        self._list_url = cfg["list_url"]
        self._link_selector = cfg.get("link_selector", "a")
        self._include = re.compile(cfg.get("include", r"(alienazion|vendita|asta pubblica|dismission)"), re.I)
        self._exclude = re.compile(cfg.get("exclude", r"(esito|locazion|concession|affitt)"), re.I)
        self._text_selector = cfg.get("text_selector")
        self._seller = cfg.get("seller", self.name)
        self._max_items = int(cfg.get("max_items", 20))

    def notice_id(self, url: str) -> str:
        return f"{self.name}:{hashlib.sha1(url.encode()).hexdigest()[:16]}"

    def candidate_links(self, html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        links: dict[str, str] = {}
        for a in soup.select(self._link_selector):
            href = a.get("href")
            if not href:
                continue
            text = a.get_text(" ", strip=True)
            haystack = f"{text} {href}"
            if self._include.search(haystack) and not self._exclude.search(haystack):
                links.setdefault(urljoin(self._list_url, href), text)
        return list(links.items())[: self._max_items]

    def page_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(self._text_selector) if self._text_selector else None
        for tag in (node or soup).find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return (node or soup).get_text("\n")

    async def fetch(
        self,
        client: PoliteHTTPClient,
        cursor: Optional[str],
        known_ids: set[str],
        progress: SourceProgress,
    ) -> AsyncIterator[RawNotice]:
        from app.ingestion.discovery.pdf_extractor import extract_pdf

        listing = await client.get(self._list_url)
        listing.raise_for_status()
        for url, text in self.candidate_links(listing.text):
            nid = self.notice_id(url)
            if nid in known_ids:
                progress.skipped_known += 1
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if url.lower().endswith(".pdf") or "pdf" in resp.headers.get("content-type", ""):
                    body = extract_pdf(resp.content).text
                else:
                    body = self.page_text(resp.text)
            except Exception as exc:
                log.warning("public_sales.html_notice_error", source=self.name, url=url, error=str(exc))
                progress.errors += 1
                continue
            progress.fetched += 1
            yield RawNotice(
                notice_id=nid, source=self.name, title=text or first_line(body),
                body=body, ente=self._seller, url=url,
            )
