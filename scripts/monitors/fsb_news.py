"""Monitor implementation for Financial Stability Board news."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
import re

import requests
from bs4 import BeautifulSoup

from . import Monitor, NewsItem


class FSBNewsMonitor(Monitor):
    """Monitor that fetches news from the Financial Stability Board website."""

    BASE_URL = "https://www.fsb.org/news/"
    SOURCE = "Financial Stability Board"
    
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, Any]:
        """Retrieve the FSB news page HTML."""
        
        try:
            response = self.session.get(
                self.BASE_URL,
                timeout=10,
            )
            response.raise_for_status()
            return {"html": response.text}
        except requests.RequestException as e:
            print(f"Error fetching FSB news: {e}")
            return {"html": ""}

    def parse(self, raw_data: Dict[str, Any]) -> Iterable[NewsItem]:
        """Parse the FSB news HTML into NewsItem instances."""
        
        html = raw_data.get("html", "")
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        items: List[NewsItem] = []
        
        # Find news articles
        articles = soup.select(".post-item")
        
        for article in articles:
            try:
                # Extract title
                title_elem = article.select_one(".post-title a")
                if not title_elem:
                    continue
                    
                title = title_elem.text.strip()
                url = title_elem.get("href", "")
                
                # Extract date
                date_elem = article.select_one(".post-date")
                if not date_elem:
                    continue
                    
                date_text = date_elem.text.strip()
                date = self._parse_date(date_text)
                
                if not date:
                    continue
                
                # Extract excerpt if available
                excerpt_elem = article.select_one(".post-excerpt")
                excerpt = excerpt_elem.text.strip() if excerpt_elem else ""
                
                # Build content
                content = excerpt if excerpt else f"New FSB release: {title}"
                
                items.append(
                    NewsItem(
                        title=title,
                        source=self.SOURCE,
                        url=url,
                        date=date,
                        content=content,
                    )
                )
            except Exception as e:
                print(f"Error parsing FSB article: {e}")
                continue
            
        return items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag recent FSB news as breaking."""
        
        # Check if it's recent (within the last day)
        now = datetime.now(timezone.utc)
        is_recent = (now - item.date) <= timedelta(days=1)
        
        return is_recent

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse the date string from FSB format."""
        try:
            # Example: "4 February 2026"
            date = datetime.strptime(date_text.strip(), "%d %B %Y")
            return date.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                # Example: "04 Feb 2026"
                date = datetime.strptime(date_text.strip(), "%d %b %Y")
                return date.replace(tzinfo=timezone.utc)
            except ValueError:
                print(f"Could not parse date: {date_text}")
                return None


__all__ = ["FSBNewsMonitor"]
