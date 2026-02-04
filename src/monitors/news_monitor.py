"""
Core monitoring framework used to collect and persist news items from
heterogeneous data sources such as regulatory filings, geological alerts,
and cybersecurity advisories.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence, Set

import feedparser
import requests
from bs4 import BeautifulSoup

# Configure module level logging once so every monitor shares the same setup.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """
    Normalized representation of a single news artifact regardless of source.
    """

    source: str
    title: str
    link: str
    published_at: datetime
    summary: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def identity(self) -> str:
        """
        Unique identifier used for deduplication. Defaults to the link when
        available, otherwise falls back to a composite of key metadata.
        """
        if self.link:
            return self.link
        return f"{self.source}:{self.title}:{self.published_at.isoformat()}"


class StorageBackend(Protocol):
    """
    Lightweight protocol that storage backends must satisfy. Providing a
    protocol keeps the monitor decoupled from concrete persistence engines.
    """

    def has_item(self, item: NewsItem) -> bool:
        ...

    def persist(self, item: NewsItem) -> None:
        ...


class Monitor(ABC):
    """
    Base monitor providing common fetch/parse/store workflow with simple
    caching for duplicate detection. Specific monitors only need to override
    URL/parse logic to integrate new sources.
    """

    name: str = "base-monitor"
    source_url: Optional[str] = None
    timeout: int = 10

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        storage: Optional[StorageBackend] = None,
    ) -> None:
        self.session = session or self._create_session()
        self.storage = storage
        self._published_id_cache: Set[str] = set()

    def run_once(self) -> Sequence[NewsItem]:
        """
        Execute a single monitoring cycle, returning the newly stored items.
        """
        logger.info("Running monitor %s", self.name)
        response = self.fetch()
        items = list(self.parse(response))
        new_items: list[NewsItem] = []
        for item in items:
            if self.is_published(item):
                logger.debug("Skipping previously published item %s", item.identity())
                continue
            self.store(item)
            new_items.append(item)
        logger.info("Monitor %s stored %d new items", self.name, len(new_items))
        return new_items

    def fetch(self) -> requests.Response:
        """
        Retrieve remote content. Subclasses may override for APIs requiring
        authentication or bespoke request payloads.
        """
        if not self.source_url:
            raise ValueError(f"{self.__class__.__name__} missing source_url")
        logger.debug("Fetching %s", self.source_url)
        response = self.session.get(self.source_url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def parse(self, response: requests.Response) -> Iterable[NewsItem]:
        """
        Parse a response into `NewsItem` objects. The default implementation
        expects RSS/Atom content but can be overridden for JSON or HTML sources.
        """
        logger.debug("Parsing feed for %s", self.name)
        feed = feedparser.parse(response.content)
        for entry in feed.entries:
            yield self._feed_entry_to_item(entry)

    def store(self, item: NewsItem) -> None:
        """
        Persist a news item. By default items are logged, but any storage
        backend implementing the `StorageBackend` protocol can be injected.
        """
        if self.storage:
            self.storage.persist(item)
        else:
            logger.info("New item detected [%s]: %s", item.source, item.title)
        self._published_id_cache.add(self.item_identity(item))

    def is_published(self, item: NewsItem) -> bool:
        """
        Check whether an item has already been persisted either in-memory or
        via the configured storage backend.
        """
        identity = self.item_identity(item)
        if identity in self._published_id_cache:
            return True
        if self.storage and self.storage.has_item(item):
            self._published_id_cache.add(identity)
            return True
        return False

    def item_identity(self, item: NewsItem) -> str:
        """
        Hook to customize deduplication strategy (e.g., hash of content).
        """
        return item.identity()

    def _feed_entry_to_item(self, entry: Dict[str, Any]) -> NewsItem:
        """
        Convert a feedparser entry into a normalized `NewsItem`.
        """
        published_at = self._resolve_entry_datetime(entry)
        summary = entry.get("summary") or entry.get("description") or ""
        summary = self._clean_html(summary)
        link = entry.get("link", "")
        title = entry.get("title", "").strip()
        raw_entry = dict(entry)
        return NewsItem(
            source=self.name,
            title=title,
            link=link,
            published_at=published_at,
            summary=summary,
            raw=raw_entry,
        )

    def _resolve_entry_datetime(self, entry: Dict[str, Any]) -> datetime:
        """
        Extract a timezone-aware datetime from a feed entry, defaulting to now
        in UTC when the feed omits a timestamp.
        """
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
        date_str = entry.get("published") or entry.get("updated")
        if date_str:
            try:
                return datetime.fromisoformat(date_str)
            except ValueError:
                logger.debug("Could not parse datetime %s", date_str)
        return datetime.now(tz=timezone.utc)

    def _clean_html(self, text: str) -> str:
        """
        Strip markup from HTML fragments so summaries are consistently plain
        text across data sources.
        """
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(" ", strip=True)

    def _create_session(self) -> requests.Session:
        """
        Prepare a requests session with sensible defaults for public feeds.
        """
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "claude-3-7-news-monitor/1.0 (+https://github.com/anthropic/claude)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
            }
        )
        return session

    @abstractmethod
    def monitor_description(self) -> str:
        """
        Human-readable description of the monitor's purpose. Useful for logs
        and dashboards to summarize coverage.
        """
        raise NotImplementedError

