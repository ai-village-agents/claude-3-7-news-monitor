"""Base classes and utilities for news monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional, Protocol, runtime_checkable


@dataclass
class NewsItem:
    """Structured representation of a news item."""

    title: str
    source: str
    url: str
    date: datetime
    content: str = ""


@runtime_checkable
class Monitor(Protocol):
    """Protocol defining the interface for news monitors."""

    def fetch(self) -> Dict:
        """Fetch raw data from source(s)."""
        ...

    def parse(self, raw_data: Dict) -> Iterable[NewsItem]:
        """Parse raw data into structured news items."""
        ...


__all__ = ["NewsItem", "Monitor"]
