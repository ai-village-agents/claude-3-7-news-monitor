#!/usr/bin/env python3

"""
Monitor for European Commission Decisions
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

class EUCommissionMonitor(Monitor):
    """Monitor for European Commission decisions and announcements"""

    def __init__(self):
        super().__init__()
        self.name = "EU Commission Monitor"
        self.source_id = "eu-commission"
        self.cache_ttl = 3600  # 1 hour cache
        self.max_items = 15
        self.press_url = "https://ec.europa.eu/commission/presscorner/home/en"

    def monitor_description(self) -> str:
        """Human-readable description of the monitor's purpose"""
        return "Monitors European Commission for new decisions and announcements"

    def fetch(self) -> str:
        """Fetch the EU Commission press corner"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(self.press_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching EU Commission page: {e}")
            return ""

    def parse(self, content: str) -> List[NewsItem]:
        """Parse the EU Commission press page for recent announcements"""
        if not content:
            return []

        try:
            items = []
            soup = BeautifulSoup(content, "html.parser")
            
            # Find all press releases
            press_items = soup.select(".ecl-content-item")
            
            for item in press_items[:self.max_items]:  # Limit to max_items
                try:
                    # Extract date
                    date_element = item.select_one(".ecl-content-item__date")
                    date_str = date_element.text.strip() if date_element else ""
                    
                    # Extract title and link
                    title_element = item.select_one(".ecl-content-item__title a")
                    if not title_element:
                        continue
                        
                    title = title_element.text.strip()
                    link = title_element.get("href", "")
                    
                    # Extract type (e.g., Press release, Statement, etc.)
                    type_element = item.select_one(".ecl-content-item__meta-item:first-child")
                    item_type = type_element.text.strip() if type_element else "Press Release"
                    
                    # Parse date
                    try:
                        if date_str:
                            pub_date = datetime.strptime(date_str, "%d %B %Y")
                        else:
                            pub_date = datetime.now()
                    except ValueError:
                        try:
                            # Try alternative format
                            pub_date = datetime.strptime(date_str, "%d/%m/%Y")
                        except ValueError:
                            pub_date = datetime.now()
                    
                    # Create summary based on item type
                    if "antitrust" in title.lower() or "competition" in title.lower():
                        summary = f"The European Commission has issued an antitrust decision: {title}"
                        title_prefix = "EU ANTITRUST: "
                    elif "infringement" in title.lower():
                        summary = f"The European Commission has launched infringement proceedings: {title}"
                        title_prefix = "EU INFRINGEMENT: "
                    elif "state aid" in title.lower():
                        summary = f"The European Commission has made a state aid decision: {title}"
                        title_prefix = "EU STATE AID: "
                    else:
                        summary = f"The European Commission has issued a {item_type.lower()}: {title}"
                        title_prefix = "EU COMMISSION: "
                    
                    # Create raw data
                    raw_data = {
                        "title": title,
                        "link": link,
                        "date": date_str,
                        "type": item_type
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
                    logger.error(f"Error parsing EU Commission item: {e}")
            
            return items
        except Exception as e:
            logger.error(f"Error parsing EU Commission page: {e}")
            return []

    def filter_new_items(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter out items we've already seen based on link"""
        return [item for item in items if item.link not in self._published_id_cache]
