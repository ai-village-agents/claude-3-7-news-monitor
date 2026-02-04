"""Monitor implementation for U.S. Department of Justice news listings."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class DOJMonitor(Monitor):
    """Monitor that scrapes the Department of Justice newsroom."""

    SOURCE = "U.S. Department of Justice"
    SITE_ROOT = "https://www.justice.gov"
    NEWS_URL = f"{SITE_ROOT}/news"

    REQUEST_TIMEOUT = 20
    _META_REFRESH_RE = re.compile(r"URL=['\"](?P<target>[^'\"]+)['\"]", re.IGNORECASE)

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://www.justice.gov/news)",
        )

    def fetch(self) -> str:
        """Retrieve the DOJ newsroom HTML while handling Akamai verification."""

        try:
            response = self.session.get(self.NEWS_URL, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"Failed to fetch DOJ news listing: {exc}") from exc

        html = response.text
        verification_url = self._extract_verification_url(html)

        if verification_url:
            try:
                verification_response = self.session.get(
                    verification_url, timeout=self.REQUEST_TIMEOUT
                )
                verification_response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network failure
                raise RuntimeError(
                    f"Failed to complete DOJ verification challenge: {exc}"
                ) from exc
            html = verification_response.text

        return html

    def parse(self, raw_html: str) -> Iterable[NewsItem]:
        """Parse the newsroom HTML into `NewsItem` instances."""

        soup = BeautifulSoup(raw_html or "", "html.parser")
        rows = soup.select("div.rows-wrapper div.views-row")

        def iter_items() -> Iterator[NewsItem]:
            for row in rows:
                anchor = row.select_one("h2.news-title a")
                if not anchor:
                    continue

                title = anchor.get_text(strip=True)
                if not title:
                    continue

                href = anchor.get("href", "")
                url = urljoin(self.SITE_ROOT, href)

                node_type = row.select_one("div.node-type")
                summary = self._extract_summary(row)

                content_parts = []
                if node_type:
                    node_type_text = node_type.get_text(strip=True)
                    if node_type_text:
                        content_parts.append(node_type_text)
                if summary:
                    content_parts.append(summary)

                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=self._extract_published_date(row.find("time")),
                    content=" — ".join(content_parts),
                )

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published on the current UTC date as breaking news."""

        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    def _extract_published_date(self, time_tag: Optional[Tag]) -> datetime:
        """Parse the publication date from a `<time>` element."""

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
    def _extract_summary(row: Tag) -> str:
        """Return a short description if the listing provides one."""

        for selector in (".summary", ".field-formatter--text-long", ".field-formatter--text"):
            element = row.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if text:
                    return text
        return ""

    @classmethod
    def _extract_verification_url(cls, html: str) -> Optional[str]:
        """Extract the Akamai bm-verify URL if the page is behind a challenge."""

        if not html:
            return None

        match = cls._META_REFRESH_RE.search(html)
        if not match:
            return None

        target = match.group("target").strip()
        if not target:
            return None

        return urljoin(cls.SITE_ROOT, target)

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        """Attempt to parse DOJ newsroom datetime strings into UTC datetimes."""

        if not value:
            return None

        sanitized = value.replace("Z", "+00:00")

        try:
            dt = datetime.fromisoformat(sanitized)
        except ValueError:
            dt = None

        if dt:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None


__all__ = ["DOJMonitor"]
