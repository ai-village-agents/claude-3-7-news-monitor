"""Monitor implementation for U.S. Department of Justice press releases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class DOJMonitor(Monitor):
    """Monitor that scrapes DOJ press releases."""

    SOURCE = "U.S. Department of Justice"
    BASE_URL = "https://www.justice.gov/news"
    SITE_ROOT = "https://www.justice.gov"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def fetch(self) -> str:
        """Fetch the DOJ press releases page."""
        try:
            response = self.session.get(self.BASE_URL, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            return ""

    def parse(self, raw_data: str) -> Iterable[NewsItem]:
        """Parse DOJ press releases into news items."""
        if not raw_data:
            return []

        soup = BeautifulSoup(raw_data, "html.parser")
        
        for item in soup.select(".views-row"):
            try:
                # Extract title and URL
                title_elem = item.select_one("h3 a, h2 a")
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                if not title:
                    continue
                    
                url = urljoin(self.SITE_ROOT, title_elem.get("href", ""))
                
                # Extract date
                date_elem = item.select_one("time, .date-display-single")
                date_str = date_elem.get_text(strip=True) if date_elem else ""
                
                date = None
                if date_str:
                    try:
                        # Try different date formats
                        for fmt in ["%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                            try:
                                date = datetime.strptime(date_str, fmt)
                                date = date.replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                        
                if not date:
                    date = datetime.now(timezone.utc)
                
                # Extract summary
                summary_elem = item.select_one(".views-field-body .field-content")
                summary = summary_elem.get_text(strip=True) if summary_elem else ""
                
                yield NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=date,
                    content=summary,
                )
            except Exception:
                continue

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Check if a news item is breaking news (published today)."""
        if not item.date:
            return False
            
        item_dt = item.date
        if item_dt.tzinfo is None:
            item_dt = item_dt.replace(tzinfo=timezone.utc)
            
        today_utc = datetime.now(timezone.utc).date()
        return item_dt.astimezone(timezone.utc).date() == today_utc
