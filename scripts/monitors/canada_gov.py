"""Monitor implementation for the Government of Canada's consolidated news feed."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class CanadaGovMonitor(Monitor):
    """Monitor that scrapes the Government of Canada's news listings."""

    BASE_URL = "https://www.canada.ca/en/news.html"
    RESULTS_URL = "https://www.canada.ca/en/news/advanced-news-search/news-results.html"
    SOURCE = "Government of Canada"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> str:
        """Retrieve the most recent news search results page."""

        try:
            response = self.session.get(
                self.RESULTS_URL,
                params={"idx": 0},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError("Unable to retrieve Canada.ca news listings") from exc

        return response.text

    def parse(self, raw_data: str) -> Iterable[NewsItem]:
        """Parse the Canada.ca news HTML into `NewsItem` instances."""

        soup = BeautifulSoup(raw_data, "html.parser")

        def iter_items() -> Iterator[NewsItem]:
            for article in soup.select("article.item"):
                title_link = article.select_one("h3 a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                href = title_link.get("href", "")
                url = urljoin(self.BASE_URL, href)

                summary = self._extract_summary(article)

                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=self._extract_published_date(article),
                    content=summary,
                )

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published today as breaking news."""

        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    def _extract_summary(self, article: Tag) -> str:
        """Extract the summary paragraph for an article."""

        summary_paragraphs = article.find_all("p")
        if not summary_paragraphs:
            return ""
        if len(summary_paragraphs) > 1:
            return summary_paragraphs[1].get_text(" ", strip=True)
        return summary_paragraphs[0].get_text(" ", strip=True)

    def _extract_published_date(self, article: Tag) -> datetime:
        """Extract the publication date from an article element."""

        time_tag = article.find("time")
        if time_tag:
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
        """Attempt to parse Canada.ca date strings into UTC datetimes."""

        if not value:
            return None

        for fmt in ("%Y-%m-%d", "%d %B %Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        try:
            dt_iso = datetime.fromisoformat(value)
        except ValueError:
            return None

        return dt_iso if dt_iso.tzinfo else dt_iso.replace(tzinfo=timezone.utc)


__all__ = ["CanadaGovMonitor"]
