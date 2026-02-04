"""Monitor implementation for U.S. Treasury and OFAC announcements."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class TreasuryOFACMonitor(Monitor):
    """Monitor that scrapes Treasury press releases and OFAC recent actions."""

    TREASURY_SOURCE = "U.S. Treasury Department"
    OFAC_SOURCE = "Office of Foreign Assets Control"

    TREASURY_URL = "https://home.treasury.gov/news/press-releases"
    TREASURY_SITE_ROOT = "https://home.treasury.gov"
    OFAC_URL = "https://ofac.treasury.gov/recent-actions/"
    OFAC_SITE_ROOT = "https://ofac.treasury.gov"

    REQUEST_TIMEOUT = 20

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://home.treasury.gov/)",
        )

    def fetch(self) -> Dict[str, str]:
        """Retrieve the Treasury and OFAC listing pages."""

        pages: Dict[str, str] = {}
        for key, url in (("treasury", self.TREASURY_URL), ("ofac", self.OFAC_URL)):
            try:
                response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
                response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network failures
                raise RuntimeError(f"Failed to fetch {key} announcements: {exc}") from exc
            pages[key] = response.text
        return pages

    def parse(self, raw_data: Dict[str, str]) -> Iterable[NewsItem]:
        """Parse both Treasury and OFAC pages into `NewsItem` instances."""

        treasury_html = raw_data.get("treasury", "")
        ofac_html = raw_data.get("ofac", "")

        def iter_items() -> Iterator[NewsItem]:
            yield from self._parse_treasury(treasury_html)
            yield from self._parse_ofac(ofac_html)

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published on the current UTC date as breaking."""

        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    def _parse_treasury(self, html: str) -> Iterator[NewsItem]:
        """Extract news items from Treasury press release listings."""

        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("div.view-content div.mm-news-row"):
            title_link = row.select_one(".news-title a")
            if not title_link:
                continue

            title = title_link.get_text(strip=True)
            if not title:
                continue

            href = title_link.get("href", "")
            url = urljoin(self.TREASURY_SITE_ROOT, href)

            published = self._extract_time_tag(row.find("time"))

            yield NewsItem(
                title=title,
                source=self.TREASURY_SOURCE,
                url=url,
                date=published,
                content="",
            )

    def _parse_ofac(self, html: str) -> Iterator[NewsItem]:
        """Extract recent actions from the OFAC listing."""

        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("div.view-content .views-row"):
            title_link = row.find("a")
            if not title_link:
                continue

            title = title_link.get_text(strip=True)
            if not title:
                continue

            href = title_link.get("href", "")
            url = urljoin(self.OFAC_SITE_ROOT, href)

            date_text, category = self._extract_ofac_meta(row)

            yield NewsItem(
                title=title,
                source=self.OFAC_SOURCE,
                url=url,
                date=self._parse_datetime(date_text) or datetime.now(timezone.utc),
                content=category,
            )

    @staticmethod
    def _extract_ofac_meta(row: Tag) -> Tuple[str, str]:
        """Return the published date string and category text from an OFAC row."""

        meta_div = row.find("div", class_="margin-top-1")
        if not meta_div:
            return "", ""

        text = meta_div.get_text(" ", strip=True)
        if " - " in text:
            date_text, remainder = text.split(" - ", 1)
            return date_text.strip(), remainder.strip()

        return text.strip(), ""

    @staticmethod
    def _extract_time_tag(time_tag: Optional[Tag]) -> datetime:
        """Parse datetime information from a Treasury `<time>` element."""

        if not time_tag:
            return datetime.now(timezone.utc)

        candidates = [
            (time_tag.get("datetime") or "").strip(),
            time_tag.get_text(strip=True),
        ]

        for candidate in candidates:
            parsed = TreasuryOFACMonitor._parse_datetime(candidate)
            if parsed:
                return parsed

        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        """Attempt to parse Treasury/OFAC datetime strings into UTC datetimes."""

        if not value:
            return None

        sanitized = value.replace("Z", "+00:00")

        try:
            dt_iso = datetime.fromisoformat(sanitized)
        except ValueError:
            dt_iso = None

        if dt_iso:
            return dt_iso if dt_iso.tzinfo else dt_iso.replace(tzinfo=timezone.utc)

        for fmt in ("%B %d, %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None


__all__ = ["TreasuryOFACMonitor"]
