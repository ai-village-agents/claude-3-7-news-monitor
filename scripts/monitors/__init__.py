"""Core interfaces and data structures for news monitoring scripts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, List


@dataclass
class NewsItem:
    """Structured representation of a single news article or alert."""

    title: str
    source: str
    url: str
    date: datetime
    content: str
    is_breaking: bool = field(default=False)


class Monitor(ABC):
    """Abstract base class for news monitors providing a common workflow."""

    @abstractmethod
    def fetch(self) -> Any:
        """Retrieve raw data from an upstream source (network, files, etc.)."""

    @abstractmethod
    def parse(self, raw_data: Any) -> Iterable[NewsItem]:
        """Normalize the raw data into an iterable of `NewsItem` instances."""

    @abstractmethod
    def check_if_breaking(self, item: NewsItem) -> bool:
        """Determine whether a given `NewsItem` should be flagged as breaking."""

    def run(self) -> List[NewsItem]:
        """Execute the monitor workflow end-to-end and return news items."""

        raw_data = self.fetch()
        items = list(self.parse(raw_data))

        for item in items:
            item.is_breaking = self.check_if_breaking(item)

        return items
