"""Monitor implementation for Europol press releases."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from . import Monitor, NewsItem


class EuropolNewsMonitor(Monitor):
    """Monitor that fetches press releases from Europol."""

    PREFERRED_URLS = [
        "https://www.europol.europa.eu/newsroom/news-categories/press-releases",
        "https://www.europol.europa.eu/media-press/newsroom",
    ]
    API_BASE = "https://www.europol.europa.eu/cms/api"
    SOURCE = "Europol Press Releases"
    BREAKING_WINDOW = timedelta(hours=24)

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, str]:
        """Retrieve the HTML for the Europol press releases page."""

        for url in self.PREFERRED_URLS:
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200 and "window.SERVER_DATA" in response.text:
                    return {"html": response.text, "url": url}
            except requests.RequestException as exc:
                print(f"Error fetching Europol page {url}: {exc}")

        return {"html": "", "url": self.PREFERRED_URLS[-1]}

    def parse(self, raw_data: Dict[str, str]) -> Iterable[NewsItem]:
        """Parse the rendered HTML to extract press release entries."""

        html = raw_data.get("html", "")
        if not html:
            return []

        server_data = self._extract_server_data(html)
        if not server_data:
            return []

        node = server_data.get("NodeLoader", {}).get("node") or {}
        lists = node.get("lists") or []
        if not lists:
            return []

        listing = lists[0]
        items: List[Dict[str, Any]] = listing.get("items") or []
        news_items: List[NewsItem] = []

        for item in items:
            title = item.get("title")
            alias = item.get("alias")
            published = item.get("published")

            if not title or not alias or not published:
                continue

            url = urljoin("https://www.europol.europa.eu", alias)
            published_dt = datetime.fromtimestamp(published, tz=timezone.utc)
            content = self._build_content(alias)

            news_items.append(
                NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=published_dt,
                    content=content,
                )
            )

        return news_items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag press releases published within the recent window as breaking."""

        now = datetime.now(timezone.utc)
        return (now - item.date) <= self.BREAKING_WINDOW

    def _extract_server_data(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract and decode the SERVER_DATA payload embedded in the page."""

        match = re.search(r"window\.SERVER_DATA=(\{.*?\});", html, re.DOTALL)
        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            print(f"Failed to decode Europol SERVER_DATA: {exc}")
            return None

    def _build_content(self, alias: str) -> str:
        """Retrieve additional details for a press release and format summary text."""

        detail = self._fetch_detail(alias)
        if not detail:
            return ""

        intro_html = detail.get("introduction") or detail.get("summary") or ""
        intro_text = ""
        if intro_html:
            intro_text = self._html_to_text(intro_html)

        extra_parts: List[str] = []

        article_type = detail.get("articleType", {})
        if isinstance(article_type, dict) and article_type.get("title"):
            extra_parts.append(f"Type: {article_type['title']}")

        crime_areas = detail.get("crimeAreas") or []
        if crime_areas:
            titles = [area.get("title") for area in crime_areas if area.get("title")]
            if titles:
                extra_parts.append("Crime Areas: " + ", ".join(titles))

        sections = [intro_text] if intro_text else []
        if extra_parts:
            sections.append(" | ".join(extra_parts))

        return " ".join(section for section in sections if section).strip()

    def _fetch_detail(self, alias: str) -> Dict[str, Any]:
        """Fetch the detail JSON for a single press release."""

        if not alias:
            return {}

        api_url = f"{self.API_BASE}/node?url={quote(alias, safe='')}"
        try:
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            detail = response.json()
            if isinstance(detail, dict):
                return detail
        except (requests.RequestException, ValueError) as exc:
            print(f"Error fetching Europol detail for {alias}: {exc}")

        return {}

    def _html_to_text(self, html_fragment: str) -> str:
        """Convert small HTML fragments into plain text."""

        soup = BeautifulSoup(html_fragment, "html.parser")
        return soup.get_text(" ", strip=True)


__all__ = ["EuropolNewsMonitor"]
