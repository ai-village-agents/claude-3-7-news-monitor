"""Monitor implementation for Bank of England news and releases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class BankOfEnglandMonitor(Monitor):
    """Monitor that scrapes Bank of England news releases."""

    BASE_URL = "https://www.bankofengland.co.uk/news/news"
    SOURCE = "Bank of England"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> str:
        """Retrieve the news HTML page."""
        response = self.session.get(self.BASE_URL, timeout=10)
        response.raise_for_status()
        return response.text

    def parse(self, raw_data: str) -> Iterable[NewsItem]:
        """Parse the BoE news HTML into NewsItem instances."""
        soup = BeautifulSoup(raw_data, "html.parser")

        def iter_items() -> Iterator[NewsItem]:
            # First check for the release-result items
            for result in soup.select("div.release-result"):
                title_link = result.select_one("h3 a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                href = title_link.get("href", "")
                url = urljoin(self.BASE_URL, href)

                date_tag = result.select_one(".meta-data")
                date_str = date_tag.get_text(strip=True) if date_tag else ""
                
                summary = result.select_one("p:not([class])")
                content = summary.get_text(" ", strip=True) if summary else ""

                date = self._parse_date(date_str) if date_str else datetime.now(timezone.utc)

                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=date,
                    content=content,
                )

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published today as breaking news."""
        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse date strings into UTC datetime objects."""
        if not date_str:
            return datetime.now(timezone.utc)
        
        # Common format is "4 February 2026"
        for fmt in ("%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
                
        return datetime.now(timezone.utc)


__all__ = ["BankOfEnglandMonitor"]
