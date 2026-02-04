#!/usr/bin/env python3

"""
Monitor for Department of Justice Press Releases
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

class DOJMonitor(Monitor):
    """Monitor for Department of Justice press releases"""

    def __init__(self):
        super().__init__()
        self.name = "DOJ Monitor"
        self.source_id = "doj-press"
        self.cache_ttl = 3600  # 1 hour cache
        self.max_items = 10
        self.base_url = "https://www.justice.gov"
        self.press_url = "https://www.justice.gov/news"

    def monitor_description(self) -> str:
        """Human-readable description of the monitor's purpose"""
        return "Monitors Department of Justice for new press releases"

    def fetch(self) -> str:
        """Fetch the DOJ press releases page"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(self.press_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching DOJ press page: {e}")
            return ""

    def parse(self, content: str) -> List[NewsItem]:
        """Parse the DOJ press releases page for recent announcements"""
        if not content:
            return []

        try:
            items = []
            soup = BeautifulSoup(content, "html.parser")
            
            # Find all recent press releases
            press_items = soup.select(".views-row")
            
            for item in press_items[:self.max_items]:  # Limit to max_items
                try:
                    # Extract date
                    date_element = item.select_one(".field-content time")
                    date_str = date_element.text.strip() if date_element else ""
                    
                    # Extract title and link
                    title_element = item.select_one("h3.field--name-title a")
                    if not title_element:
                        continue
                        
                    title = title_element.text.strip()
                    relative_link = title_element.get("href", "")
                    link = self.base_url + relative_link if relative_link.startswith("/") else relative_link
                    
                    # Extract component (e.g., FBI, Civil Rights Division, etc.)
                    component_element = item.select_one(".field--name-field-pr-component")
                    component = component_element.text.strip() if component_element else "Department of Justice"
                    
                    # Parse date
                    try:
                        if date_str:
                            pub_date = datetime.strptime(date_str, "%B %d, %Y")
                        else:
                            pub_date = datetime.now()
                    except ValueError:
                        pub_date = datetime.now()
                    
                    # Create summary
                    summary = f"The {component} has issued a press release: {title}"
                    
                    # Create raw data
                    raw_data = {
                        "title": title,
                        "link": link,
                        "date": date_str,
                        "component": component
                    }
                    
                    # Check if this is a recent announcement (within the last 24 hours)
                    if datetime.now() - pub_date <= timedelta(hours=24):
                        # Add keywords to title for important cases
                        if any(keyword in title.lower() for keyword in ["arrest", "charged", "indicted", "sentenced", "conviction", "fraud", "terrorism"]):
                            title_prefix = "DOJ MAJOR CASE: "
                        else:
                            title_prefix = "DOJ: "
                            
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
                    logger.error(f"Error parsing DOJ press item: {e}")
            
            return items
        except Exception as e:
            logger.error(f"Error parsing DOJ press page: {e}")
            return []

    def filter_new_items(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter out items we've already seen based on link"""
        return [item for item in items if item.link not in self._published_id_cache]
