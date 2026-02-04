"""Monitor implementation for international courts (ICC, ECHR, ICJ, PCA)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, Iterator, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class InternationalCourtsMonitor(Monitor):
    """Monitor that scrapes recent updates from major international courts."""

    ICC_URL = "https://www.icc-cpi.int/news"
    ECHR_RSS_URL = "https://hudoc.echr.coe.int/app/transform/rss"
    ICJ_URL = "https://www.icj-cij.org/en/press-releases"
    PCA_URL = "https://pca-cpa.org/en/news/"

    SOURCE_ICC = "International Criminal Court (ICC)"
    SOURCE_ECHR = "European Court of Human Rights (ECHR)"
    SOURCE_ICJ = "International Court of Justice (ICJ)"
    SOURCE_PCA = "Permanent Court of Arbitration (PCA)"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "claude-news-monitor/1.0 "
            "(+https://ai-village-agents.github.io/claude-3-7-news-monitor/)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        for key, value in self.DEFAULT_HEADERS.items():
            self.session.headers.setdefault(key, value)

    def fetch(self) -> Dict[str, str]:
        """Collect raw payloads for each monitored court."""

        return {
            "icc": self._fetch_icc(),
            "echr": self._fetch_echr(),
            "icj": self._fetch_generic(self.ICJ_URL),
            "pca": self._fetch_generic(self.PCA_URL),
        }

    def parse(self, raw_data: Dict[str, str]) -> Iterable[NewsItem]:
        """Parse all court payloads into a unified iterable of news items."""

        raw_data = raw_data or {}

        def iter_items() -> Iterator[NewsItem]:
            yield from self._parse_icc(raw_data.get("icc", ""))
            yield from self._parse_echr(raw_data.get("echr", ""))
            yield from self._parse_icj(raw_data.get("icj", ""))
            yield from self._parse_pca(raw_data.get("pca", ""))

        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published today (UTC) as breaking news."""

        item_dt = item.date
        if item_dt.tzinfo is None:
            item_dt = item_dt.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_dt.astimezone(timezone.utc).date() == today_utc

    # ----------------------------------------------------------------------
    # Fetch helpers
    # ----------------------------------------------------------------------

    def _fetch_generic(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""

    def _fetch_icc(self) -> str:
        """Fetch ICC news page, allowing Cloudflare or similar hurdles."""

        try:
            response = self.session.get(
                self.ICC_URL,
                timeout=20,
                headers={
                    **self.session.headers,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                },
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""

    def _fetch_echr(self) -> str:
        """Fetch ECHR judgments feed using the HUDOC RSS transformer."""

        params = {
            "library": "echreng",
            "query": (
                "contentsitename:ECHR AND "
                "(documentcollectionid2:\"GRANDCHAMBER\" "
                "OR documentcollectionid2:\"CHAMBER\" "
                "OR documentcollectionid2:\"DECISIONS\") "
                "AND languageisocode:ENG"
            ),
            "select": "itemid,docname,doctype,documentcollectionid2,languageisocode,kpdate",
            "sort": "kpdate DESC",
            "start": 0,
            "length": 25,
        }

        try:
            response = self.session.get(
                self.ECHR_RSS_URL,
                params=params,
                timeout=20,
                headers={
                    **self.session.headers,
                    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""

    # ----------------------------------------------------------------------
    # Parser helpers
    # ----------------------------------------------------------------------

    def _parse_icc(self, raw_html: str) -> Iterator[NewsItem]:
        if not raw_html:
            return iter(())

        soup = BeautifulSoup(raw_html, "html.parser")
        candidates = soup.select("div.view-content div.views-row, article.news-item")

        def iter_items() -> Iterator[NewsItem]:
            for node in candidates:
                title_link = self._find_first_link(node)
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                url = urljoin(self.ICC_URL, title_link.get("href", "").strip())
                date = self._extract_date_generic(
                    node,
                    selectors=[
                        "time",
                        ".views-field-created",
                        ".views-field-field-publication-date",
                        ".date",
                    ],
                    default_tz=timezone.utc,
                )

                summary = self._extract_summary(
                    node,
                    selectors=[
                        ".views-field-body",
                        ".field-content",
                        "p",
                    ],
                )

                yield NewsItem(
                    title=title,
                    source=self.SOURCE_ICC,
                    url=url,
                    date=date,
                    content=summary,
                )

        return iter_items()

    def _parse_echr(self, raw_feed: str) -> Iterator[NewsItem]:
        if not raw_feed:
            return iter(())

        soup = BeautifulSoup(raw_feed, "xml")
        items = soup.find_all("item")

        def iter_items() -> Iterator[NewsItem]:
            for item in items:
                title_tag = item.find("title")
                link_tag = item.find("link")
                date_tag = item.find("pubDate")

                if not title_tag or not link_tag or not date_tag:
                    continue

                title = title_tag.get_text(strip=True)
                url = link_tag.get_text(strip=True)
                date = self._parse_rfc2822(date_tag.get_text())

                description_tag = item.find("description")
                description = (
                    description_tag.get_text(" ", strip=True) if description_tag else ""
                )

                yield NewsItem(
                    title=title,
                    source=self.SOURCE_ECHR,
                    url=url,
                    date=date,
                    content=description,
                )

        return iter_items()

    def _parse_icj(self, raw_html: str) -> Iterator[NewsItem]:
        if not raw_html:
            return iter(())

        soup = BeautifulSoup(raw_html, "html.parser")
        rows = soup.select("div.view-content div.views-row")

        def iter_items() -> Iterator[NewsItem]:
            for row in rows:
                long_title = row.select_one(
                    ".views-field-field-document-long-title .field-content"
                )
                link_tag = row.select_one(
                    ".views-field-field-press-release-number a, .views-field-title a"
                )
                time_tag = row.find("time")

                if not long_title or not link_tag or not time_tag:
                    continue

                title = long_title.get_text(" ", strip=True)
                url = urljoin(self.ICJ_URL, link_tag.get("href", "").strip())
                date = self._parse_datetime(time_tag.get("datetime"), time_tag.get_text())

                summary = self._extract_summary(
                    row,
                    selectors=[
                        ".views-field-field-document-long-title p",
                        ".views-field-field-summary",
                    ],
                )

                yield NewsItem(
                    title=title,
                    source=self.SOURCE_ICJ,
                    url=url,
                    date=date,
                    content=summary or title,
                )

        return iter_items()

    def _parse_pca(self, raw_html: str) -> Iterator[NewsItem]:
        if not raw_html:
            return iter(())

        soup = BeautifulSoup(raw_html, "html.parser")
        articles = soup.select("article.news-item")

        def iter_items() -> Iterator[NewsItem]:
            for article in articles:
                title_link = article.find("a", href=True)
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                url = urljoin(self.PCA_URL, title_link["href"].strip())

                date_container = article.select_one(".date, time")
                date_text = date_container.get_text(strip=True) if date_container else ""
                date = self._parse_date_with_formats(
                    date_text,
                    ("%d %B %Y", "%d %b %Y"),
                    default=datetime.now(timezone.utc),
                )

                summary = self._extract_summary(
                    article,
                    selectors=["p", ".news-item-content p"],
                )

                yield NewsItem(
                    title=title,
                    source=self.SOURCE_PCA,
                    url=url,
                    date=date,
                    content=summary,
                )

        return iter_items()

    # ----------------------------------------------------------------------
    # Utility helpers
    # ----------------------------------------------------------------------

    def _find_first_link(self, node: Tag) -> Optional[Tag]:
        for selector in ("h2 a", "h3 a", "h4 a", "a"):
            link = node.select_one(selector)
            if link and link.get("href"):
                return link
        return None

    def _extract_summary(self, node: Tag, selectors: List[str]) -> str:
        for selector in selectors:
            summary_nodes = node.select(selector)
            if not summary_nodes:
                continue

            texts = [
                summary_node.get_text(" ", strip=True)
                for summary_node in summary_nodes
                if summary_node.get_text(strip=True)
            ]
            if texts:
                return " ".join(dict.fromkeys(texts))

        return ""

    def _extract_date_generic(
        self,
        node: Tag,
        selectors: List[str],
        default_tz: timezone,
    ) -> datetime:
        for selector in selectors:
            element = node.select_one(selector)
            if not element:
                continue

            iso_candidate = element.get("datetime")
            if iso_candidate:
                parsed = self._parse_datetime(iso_candidate, element.get_text())
                if parsed:
                    return parsed

            text_candidate = element.get_text(strip=True)
            parsed = self._parse_date_with_formats(
                text_candidate,
                ("%d %B %Y", "%d %b %Y", "%B %d, %Y"),
                default=datetime.now(default_tz),
            )
            if parsed:
                return parsed

        return datetime.now(default_tz)

    def _parse_datetime(self, primary: Optional[str], fallback_text: Optional[str]) -> datetime:
        candidates = [primary or "", fallback_text or ""]
        for value in candidates:
            parsed = self._parse_iso_datetime(value)
            if parsed:
                return parsed

        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_iso_datetime(value: str) -> Optional[datetime]:
        if not value:
            return None

        cleaned = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return None

        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_date_with_formats(
        value: str,
        formats: Iterable[str],
        default: Optional[datetime] = None,
    ) -> datetime:
        if value:
            for fmt in formats:
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

        return (default or datetime.now(timezone.utc)).replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_rfc2822(value: str) -> datetime:
        if not value:
            return datetime.now(timezone.utc)

        try:
            dt = parsedate_to_datetime(value.strip())
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


__all__ = ["InternationalCourtsMonitor"]

