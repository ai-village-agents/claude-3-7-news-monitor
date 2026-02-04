"""Monitor implementation for NASDAQ trade halts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
import re
import xml.etree.ElementTree as ET
from io import StringIO

import requests
import feedparser

from . import Monitor, NewsItem


class NasdaqTradeHaltsMonitor(Monitor):
    """Monitor that fetches NASDAQ trade halts from their RSS feed."""

    RSS_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
    SOURCE = "NASDAQ Trade Halts"
    
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, Any]:
        """Retrieve the NASDAQ trade halts RSS feed."""
        
        try:
            response = self.session.get(
                self.RSS_URL,
                timeout=10,
            )
            response.raise_for_status()
            return {"rss": response.text}
        except requests.RequestException as e:
            print(f"Error fetching NASDAQ trade halts: {e}")
            return {"rss": ""}

    def parse(self, raw_data: Dict[str, Any]) -> Iterable[NewsItem]:
        """Parse the NASDAQ trade halts RSS into NewsItem instances."""
        
        rss_content = raw_data.get("rss", "")
        if not rss_content:
            return []
        
        # Use feedparser to parse RSS
        feed = feedparser.parse(rss_content)
        items: List[NewsItem] = []
        
        for entry in feed.entries:
            try:
                title = entry.title
                link = entry.link
                published_str = entry.published if hasattr(entry, "published") else ""
                
                # Parse date
                pub_date = None
                if published_str:
                    try:
                        # RFC 2822 format used by RSS
                        pub_date = datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %z")
                    except ValueError:
                        try:
                            # Alternative format
                            pub_date = datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %Z")
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                        except ValueError:
                            print(f"Could not parse date: {published_str}")
                            # Use current time as fallback
                            pub_date = datetime.now(timezone.utc)
                else:
                    # Use current time as fallback
                    pub_date = datetime.now(timezone.utc)
                
                # Extract content from description
                content = ""
                if hasattr(entry, "description"):
                    # Remove HTML tags
                    content = re.sub(r'<[^>]+>', ' ', entry.description)
                    content = re.sub(r'\s+', ' ', content).strip()
                
                if not content:
                    content = f"NASDAQ Trade Halt: {title}"
                
                items.append(
                    NewsItem(
                        title=title,
                        source=self.SOURCE,
                        url=link,
                        date=pub_date,
                        content=content,
                    )
                )
                
            except Exception as e:
                print(f"Error parsing NASDAQ trade halt item: {e}")
                continue
            
        return items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag recent NASDAQ trade halts as breaking news."""
        
        # Check if it's recent (within the last 6 hours)
        now = datetime.now(timezone.utc)
        is_recent = (now - item.date) <= timedelta(hours=6)
        
        return is_recent


__all__ = ["NasdaqTradeHaltsMonitor"]
