#!/usr/bin/env python3

"""
Monitor for FCC Decisions and Announcements
"""

import logging
import re
import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from typing import List, Optional

from src.monitors.news_monitor import Monitor, NewsItem

logger = logging.getLogger(__name__)

class FCCMonitor(Monitor):
    """Monitor for FCC regulatory decisions and announcements"""

    def __init__(self):
        super().__init__()
        self.name = "FCC Monitor"
        self.source_id = "fcc"
        self.cache_ttl = 3600  # 1 hour cache
        self.max_items = 15
        self.fcc_url = "https://www.fcc.gov/news-events/latest-news"

    def monitor_description(self) -> str:
        """Human-readable description of the monitor's purpose"""
        return "Monitors FCC for new regulatory decisions and announcements"

    def fetch(self) -> str:
        """Fetch the FCC latest news page"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(self.fcc_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching FCC news page: {e}")
            return ""

    def parse(self, content: str) -> List[NewsItem]:
        """Parse the FCC news page for recent announcements"""
        if not content:
            return []

        try:
            items = []
            soup = BeautifulSoup(content, "html.parser")
            
            # Find all news items
            news_items = soup.select(".views-row")
            
            for item in news_items[:self.max_items]:  # Limit to max_items
                try:
                    # Extract date
                    date_element = item.select_one(".datetime")
                    date_str = date_element.text.strip() if date_element else ""
                    
                    # Extract title and link
                    title_element = item.select_one("h4.views-field-title a")
                    if not title_element:
                        continue
                        
                    title = title_element.text.strip()
                    relative_link = title_element.get("href", "")
                    base_url = "https://www.fcc.gov"
                    link = base_url + relative_link if relative_link.startswith("/") else relative_link
                    
                    # Extract document type (if available)
                    doc_type_element = item.select_one(".document-type")
                    doc_type = doc_type_element.text.strip() if doc_type_element else "News Release"
                    
                    # Parse date
                    try:
                        if date_str:
                            pub_date = datetime.strptime(date_str, "%m/%d/%Y")
                        else:
                            pub_date = datetime.now()
                    except ValueError:
                        pub_date = datetime.now()
                    
                    # Determine if this is a major regulatory decision
                    is_major = False
                    major_keywords = ["order", "spectrum", "broadband", "5g", "auction", "rule", "decision", "authority", "vote", "commissioner"]
                    if any(keyword in title.lower() for keyword in major_keywords):
                        is_major = True
                    
                    # Create summary
                    if is_major:
                        summary = f"The FCC has issued a major regulatory decision: {title}"
                        title_prefix = "FCC MAJOR DECISION: "
                    else:
                        summary = f"The FCC has issued a {doc_type.lower()}: {title}"
                        title_prefix = "FCC: "
                    
                    # Create raw data
                    raw_data = {
                        "title": title,
                        "link": link,
                        "date": date_str,
                        "document_type": doc_type,
                        "is_major": is_major
                    }
                    
                    # Check if this is a recent announcement (within the last 48 hours)
                    if datetime.now() - pub_date <= timedelta(hours=48):
                        items.append(
                            NewsItem(
                                title=f"{title_prefix}{title}",
                                summary=summary,
                                link=link,
                                source=self.source_id,
                                published_at=pub_date,
                                raw=raw_data,
                            )
                        )
                except Exception as e:
                    logger.error(f"Error parsing FCC news item: {e}")
            
            return items
        except Exception as e:
            logger.error(f"Error parsing FCC news page: {e}")
            return []

    def filter_new_items(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter out items we've already seen based on link"""
        return [item for item in items if item.link not in self._published_id_cache]
