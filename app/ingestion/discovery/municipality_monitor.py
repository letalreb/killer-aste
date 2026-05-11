"""
Municipality monitor — strategies for discovering public opportunities.

Architecture:
  BaseMonitor          — abstract base class defining the discovery interface
  GenericJsonApiMonitor — fetches a JSON array from a configured endpoint
  GenericRssMonitor    — parses RSS/Atom feeds for public notices
  PNRRMonitor          — Italia Domani open-data for PNRR projects

Each monitor returns a list of raw dicts; the caller passes them through
opportunity_parser.parse_opportunity() to get structured data.

Configuration lives in config.yaml under enrichment.monitors:
  monitors:
    - type: json_api
      name: my_source
      url: https://...
      fields:                    # key remapping from API → canonical
        title: titolo
        description: descrizione
        province: provincia
        budget: importo
        source_url: link
    - type: rss
      name: comune_bologna
      url: https://...
    - type: pnrr
      enabled: true
      provinces: [BO, MI, RM]   # filter; empty/absent = all
"""
from __future__ import annotations

from typing import Optional

import structlog
from bs4 import BeautifulSoup

from app.ingestion.http_client import AntiBanHTTPClient

log = structlog.get_logger(__name__)


class BaseMonitor:
    name: str = "base"

    async def discover(
        self,
        client: AntiBanHTTPClient,
        provinces: Optional[list[str]] = None,
    ) -> list[dict]:
        """Discover opportunities. Returns raw dicts for opportunity_parser."""
        raise NotImplementedError


# ── Generic JSON API monitor ──────────────────────────────────────────────────

class GenericJsonApiMonitor(BaseMonitor):
    """
    Fetches a JSON endpoint that returns an array (or paginated object) of
    public opportunities.

    Field mapping lets the YAML config remap API-specific key names to the
    canonical keys parse_opportunity() expects (title, description, province,
    city, budget, source_url, document_url).
    """

    def __init__(self, cfg: dict) -> None:
        self.name = cfg.get("name", "json_api")
        self._url = cfg["url"]
        self._field_map: dict[str, str] = cfg.get("fields", {})
        self._array_key: Optional[str] = cfg.get("array_key")  # e.g. "results"
        self._province_filter: list[str] = [
            p.upper() for p in cfg.get("provinces", [])
        ]

    async def discover(
        self,
        client: AntiBanHTTPClient,
        provinces: Optional[list[str]] = None,
    ) -> list[dict]:
        effective_filter = (
            [p.upper() for p in provinces] if provinces else self._province_filter
        )
        try:
            resp = await client.get(self._url)
            if resp.status_code != 200:
                log.debug("json_api_monitor.non_200", name=self.name, status=resp.status_code)
                return []
            data = resp.json()
        except Exception as exc:
            log.debug("json_api_monitor.fetch_failed", name=self.name, error=str(exc))
            return []

        items = data
        if self._array_key and isinstance(data, dict):
            items = data.get(self._array_key, [])
        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            remapped = self._remap(item)
            if effective_filter:
                prov = remapped.get("province", "")
                if prov and prov.upper() not in effective_filter:
                    continue
            results.append(remapped)
        return results

    def _remap(self, item: dict) -> dict:
        if not self._field_map:
            return item
        out = dict(item)
        for canonical, api_key in self._field_map.items():
            if api_key in item:
                out[canonical] = item[api_key]
        return out


# ── RSS / Atom monitor ────────────────────────────────────────────────────────

class GenericRssMonitor(BaseMonitor):
    """
    Parses RSS 2.0 or Atom 1.0 feeds published by Italian municipalities for
    their Albo Pretorio or public notice boards.

    Each <item>/<entry> becomes one raw dict with keys:
      title, description, source_url, date
    """

    def __init__(self, cfg: dict) -> None:
        self.name = cfg.get("name", "rss")
        self._url = cfg["url"]
        self._province: Optional[str] = cfg.get("province")
        self._city: Optional[str] = cfg.get("city")

    async def discover(
        self,
        client: AntiBanHTTPClient,
        provinces: Optional[list[str]] = None,
    ) -> list[dict]:
        if provinces and self._province and self._province.upper() not in provinces:
            return []
        try:
            resp = await client.get(self._url)
            if resp.status_code != 200:
                return []
            return self._parse_feed(resp.text)
        except Exception as exc:
            log.debug("rss_monitor.fetch_failed", name=self.name, error=str(exc))
            return []

    def _parse_feed(self, xml: str) -> list[dict]:
        try:
            soup = BeautifulSoup(xml, "lxml-xml")
        except Exception:
            soup = BeautifulSoup(xml, "html.parser")

        items = soup.find_all("item") or soup.find_all("entry")
        results = []
        for item in items:
            title = (item.find("title") or item.find("dc:title"))
            link = item.find("link") or item.find("url")
            desc = item.find("description") or item.find("summary") or item.find("content")
            results.append({
                "title": title.get_text(strip=True) if title else "Avviso pubblico",
                "description": desc.get_text(strip=True) if desc else "",
                "source_url": (
                    link.get("href") or link.get_text(strip=True)
                    if link else None
                ),
                "province": self._province,
                "city": self._city,
            })
        return results


# ── PNRR monitor ──────────────────────────────────────────────────────────────

class PNRRMonitor(BaseMonitor):
    """
    Monitors PNRR projects from the Italia Domani open-data API.

    The public endpoint returns paginated JSON describing funded projects
    across all Italian municipalities, including location and budget data.

    Docs: https://www.italiadomani.gov.it/content/sogei-ng/it/it/open-data.html
    """

    name = "pnrr"
    _API_URL = "https://api.italiadomani.gov.it/v2/progetto"

    def __init__(self, cfg: dict) -> None:
        self._enabled = cfg.get("enabled", False)
        self._province_filter = [p.upper() for p in cfg.get("provinces", [])]
        self._max_pages = cfg.get("max_pages", 5)
        self._page_size = cfg.get("page_size", 50)

    async def discover(
        self,
        client: AntiBanHTTPClient,
        provinces: Optional[list[str]] = None,
    ) -> list[dict]:
        if not self._enabled:
            return []

        effective_filter = (
            [p.upper() for p in provinces] if provinces else self._province_filter
        )
        results: list[dict] = []

        for page in range(self._max_pages):
            params: dict = {"page": page, "size": self._page_size}
            if effective_filter:
                params["sigla_provincia"] = ",".join(effective_filter)

            try:
                resp = await client.get(self._API_URL, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
                items = data.get("content") or data.get("data") or data or []
                if not items:
                    break
                for item in items:
                    results.append(self._normalise(item))
                if data.get("last", True):
                    break
            except Exception as exc:
                log.debug("pnrr_monitor.fetch_failed", page=page, error=str(exc))
                break

        return results

    @staticmethod
    def _normalise(item: dict) -> dict:
        return {
            "title": item.get("titolo_progetto") or item.get("descrizione") or "Progetto PNRR",
            "description": item.get("descrizione_progetto") or item.get("descrizione"),
            "province": item.get("sigla_provincia") or item.get("provincia"),
            "city": item.get("comune"),
            "budget": item.get("importo_totale") or item.get("finanziamento"),
            "source_url": item.get("url") or item.get("link"),
            "completion": item.get("data_fine_prevista") or item.get("anno_completamento"),
            "extra_source": "pnrr_italia_domani",
        }


# ── Factory ───────────────────────────────────────────────────────────────────

def build_monitors(cfg: dict) -> list[BaseMonitor]:
    """
    Build a list of monitor instances from the enrichment config section.

    Expected config shape:
      enrichment:
        monitors:
          - type: json_api
            name: ...
            url: ...
          - type: rss
            ...
          - type: pnrr
            enabled: true
    """
    monitors: list[BaseMonitor] = []
    for entry in cfg.get("monitors", []):
        monitor_type = entry.get("type", "")
        try:
            if monitor_type == "json_api":
                monitors.append(GenericJsonApiMonitor(entry))
            elif monitor_type == "rss":
                monitors.append(GenericRssMonitor(entry))
            elif monitor_type == "pnrr":
                monitors.append(PNRRMonitor(entry))
            else:
                log.warning("build_monitors.unknown_type", type=monitor_type)
        except Exception as exc:
            log.warning("build_monitors.init_failed", type=monitor_type, error=str(exc))
    return monitors
