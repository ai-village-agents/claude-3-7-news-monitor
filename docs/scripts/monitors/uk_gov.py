"""Monitor implementation for GOV.UK news and communications listings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class UKGovMonitor(Monitor):
    """Monitor that scrapes the GOV.UK news and communications finder."""

    BASE_URL = "https://www.gov.uk/search/news-and-communications"
    SOURCE = "GOV.UK"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        # GOV.UK throttles generic user-agents; provide a descriptive default.
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://www.gov.uk/)",
        )

    def fetch(self) -> str:
        """Retrieve the finder HTML page ordered by most recent updates."""

        response = self.session.get(
            self.BASE_URL,
            params={"order": "updated-newest"},
            timeout=10,
        )
        response.raise_for_status()
        return response.text

    def parse(self, raw_data: str) -> Iterable[NewsItem]:
        """Parse the GOV.UK finder HTML into `NewsItem` instances."""

        soup = BeautifulSoup(raw_data, "html.parser")

        def iter_items() -> Iterator[NewsItem]:
            for li in soup.select("ul.gem-c-document-list > li.gem-c-document-list__item"):
                title_link = li.select_one(".gem-c-document-list__item-title a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                href = title_link.get("href", "")
                url = urljoin(self.BASE_URL, href)

                summary = li.select_one(".gem-c-document-list__item-description")
                content = summary.get_text(" ", strip=True) if summary else ""

                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=self._extract_published_date(li),
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

    def _extract_published_date(self, li: Tag) -> datetime:
        """Resolve the publication or update date for a GOV.UK list item."""

        time_tag = li.find("time")
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
        """Attempt to parse GOV.UK datetime strings into UTC datetimes."""

        if not value:
            return None

        sanitized = value.replace("Z", "+00:00")

        # Try full ISO-8601 first (covers values with explicit times).
        try:
            dt_iso = datetime.fromisoformat(sanitized)
        except ValueError:
            dt_iso = None

        if dt_iso:
            return dt_iso if dt_iso.tzinfo else dt_iso.replace(tzinfo=timezone.utc)

        # Fallback to the common "4 February 2026" style.
        for fmt in ("%d %B %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None


__all__ = ["UKGovMonitor"]
