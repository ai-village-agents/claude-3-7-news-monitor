"""Monitor implementation for Bank of England news listings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class BankOfEnglandMonitor(Monitor):
    """Monitor that scrapes Bank of England news releases via their JSON endpoint."""

    SOURCE = "Bank of England"
    SITE_ROOT = "https://www.bankofengland.co.uk"
    API_URL = f"{SITE_ROOT}/_api/News/RefreshPagedNewsList"

    NEWS_PAGE_ID = "{CE377CC8-BFBC-418B-B4D9-DBC1C64774A8}"
    NEWS_TYPES = ("09f8960ebc384e3589da5349744916ae",)

    def __init__(self, session: Optional[requests.Session] = None, page_size: int = 30) -> None:
        self.session = session or requests.Session()

        default_headers = requests.utils.default_headers()
        required_headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.SITE_ROOT,
            "Referer": f"{self.SITE_ROOT}/news/news",
            "X-Requested-With": "XMLHttpRequest",
        }

        for header, value in required_headers.items():
            current = self.session.headers.get(header)
            if not current or current == default_headers.get(header):
                self.session.headers[header] = value
        self.page_size = page_size

    def fetch(self) -> dict:
        """Retrieve the latest Bank of England news payload from the JSON API."""

        payload = {
            "SearchTerm": "",
            "Id": self.NEWS_PAGE_ID,
            "PageSize": str(self.page_size),
            "NewsTypes": ",".join(self.NEWS_TYPES),
            "NewsTypesAvailable": ",".join(self.NEWS_TYPES),
            "Taxonomies": "",
            "TaxonomiesAvailable": "",
            "Page": "1",
            "Direction": "1",
            "DateFrom": "",
            "DateTo": "",
            "Grid": "false",
            "InfiniteScrolling": "false",
        }

        response = self.session.post(
            self.API_URL,
            data=payload,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data: dict) -> Iterable[NewsItem]:
        """Parse the JSON payload into `NewsItem` instances."""

        html = (raw_data or {}).get("Results", "")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        def iter_items() -> Iterator[NewsItem]:
            for anchor in soup.select("a.release"):
                title = self._extract_title(anchor)
                if not title:
                    continue

                href = anchor.get("href", "")
                url = urljoin(self.SITE_ROOT, href)

                tag_text = anchor.select_one(".release-tag")
                content = tag_text.get_text(" ", strip=True) if tag_text else ""

                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=self._extract_published_date(anchor.find("time", class_="release-date")),
                    content=content,
                )

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published on the current UTC date as breaking news."""

        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    @staticmethod
    def _extract_title(anchor: Tag) -> str:
        """Extract the preferred title text from a news listing anchor."""

        title_tag = anchor.select_one("h3.list")
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title:
                return title

        fallback = anchor.get_text(" ", strip=True)
        return fallback

    def _extract_published_date(self, time_tag: Optional[Tag]) -> datetime:
        """Parse the publication date from the `<time>` element."""

        if not time_tag:
            return datetime.now(timezone.utc)

        candidates = [
            (time_tag.get("datetime") or "").strip(),
            time_tag.get_text(strip=True),
        ]

        for value in candidates:
            parsed = self._parse_datetime(value)
            if parsed:
                return parsed

        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        """Attempt to parse Bank of England datetime strings into UTC datetimes."""

        if not value:
            return None

        normalized = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            dt = None

        if dt:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None


__all__ = ["BankOfEnglandMonitor"]
