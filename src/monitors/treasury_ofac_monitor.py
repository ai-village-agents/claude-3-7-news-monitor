#!/usr/bin/env python3

"""
Monitor for U.S. Treasury OFAC Sanctions Announcements
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

class TreasuryOFACMonitor(Monitor):
    """Monitor for U.S. Treasury OFAC sanctions announcements"""

    def __init__(self):
        super().__init__()
        self.name = "Treasury OFAC Monitor"
        self.source_id = "treasury-ofac"
        self.cache_ttl = 3600  # 1 hour cache
        self.max_items = 10
        self.base_url = "https://home.treasury.gov"
        self.sanctions_url = "https://ofac.treasury.gov/recent-actions"

    def monitor_description(self) -> str:
        """Human-readable description of the monitor's purpose"""
        return "Monitors U.S. Treasury OFAC for new sanctions announcements"

    def fetch(self) -> str:
        """Fetch the recent OFAC sanctions page"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(self.sanctions_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching Treasury OFAC page: {e}")
            return ""

    def parse(self, content: str) -> List[NewsItem]:
        """Parse the OFAC sanctions page for recent announcements"""
        if not content:
            return []

        try:
            items = []
            soup = BeautifulSoup(content, "html.parser")
            
            # Find all recent actions
            recent_actions = soup.select(".views-row")
            
            for action in recent_actions[:self.max_items]:  # Limit to max_items
                try:
                    # Extract date
                    date_element = action.select_one(".datetime")
                    date_str = date_element.text.strip() if date_element else ""
                    
                    # Extract title and link
                    title_element = action.select_one("h3.field-content a")
                    if not title_element:
                        continue
                        
                    title = title_element.text.strip()
                    relative_link = title_element.get("href", "")
                    link = self.base_url + relative_link if relative_link.startswith("/") else relative_link
                    
                    # Parse date
                    try:
                        if date_str:
                            pub_date = datetime.strptime(date_str, "%m/%d/%Y")
                        else:
                            pub_date = datetime.now()
                    except ValueError:
                        pub_date = datetime.now()
                    
                    # Create summary
                    summary = f"The U.S. Department of the Treasury's Office of Foreign Assets Control (OFAC) has announced new sanctions: {title}"
                    
                    # Create raw data
                    raw_data = {
                        "title": title,
                        "link": link,
                        "date": date_str,
                        "announcement_type": "OFAC Sanctions"
                    }
                    
                    # Check if this is a recent announcement (within the last 48 hours)
                    if datetime.now() - pub_date <= timedelta(hours=48):
                        items.append(
                            NewsItem(
                                title=f"TREASURY SANCTIONS: {title}",
                                summary=summary,
                                link=link,
                                source=self.source_id,
                                published_at=pub_date,
                                raw=raw_data,
                            )
                        )
                except Exception as e:
                    logger.error(f"Error parsing OFAC sanction item: {e}")
            
            return items
        except Exception as e:
            logger.error(f"Error parsing Treasury OFAC page: {e}")
            return []

    def filter_new_items(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter out items we've already seen based on link"""
        return [item for item in items if item.link not in self._published_id_cache]
