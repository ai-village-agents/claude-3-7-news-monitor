"""
Monitor for NOAA Space Weather Prediction Center alerts.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup

from .news_monitor import Monitor, NewsItem

logger = logging.getLogger(__name__)


class NOAASWPCMonitor(Monitor):
    """
    Monitor that tracks space weather alerts from NOAA's Space Weather 
    Prediction Center.
    """

    name = "noaa-swpc"
    source_url = "https://www.swpc.noaa.gov/products/alerts-watches-and-warnings"
    timeout = 30

    def parse(self, response: requests.Response) -> Iterable[NewsItem]:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find the alert table
        tables = soup.find_all("table", class_="table")
        if not tables:
            logger.warning("No alert tables found on NOAA SWPC page")
            return []
        
        alert_table = tables[0]
        rows = alert_table.find_all("tr")
        
        # Skip header row
        for row in rows[1:]:
            try:
                item = self._row_to_item(row)
                if item:
                    yield item
            except Exception as e:
                logger.error(f"Error processing NOAA SWPC alert: {e}")
    
    def monitor_description(self) -> str:
        return (
            "Tracks space weather alerts, watches, and warnings issued by "
            "NOAA's Space Weather Prediction Center."
        )
    
    def _row_to_item(self, row) -> Optional[NewsItem]:
        """Convert a table row to a NewsItem."""
        cells = row.find_all("td")
        if len(cells) < 5:
            return None
        
        # Extract cell contents
        issue_datetime = cells[0].text.strip()
        product = cells[1].text.strip()
        message = cells[2].text.strip()
        
        # Extract link
        link_elem = cells[3].find("a")
        link = link_elem.get("href") if link_elem else ""
        if link and not link.startswith("http"):
            link = f"https://www.swpc.noaa.gov{link}"
        
        # Try to parse the issue datetime
        try:
            dt = datetime.strptime(issue_datetime, "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Could not parse datetime: {issue_datetime}")
            dt = datetime.now(timezone.utc)
        
        # Check if this is a significant alert
        alert_level = self._extract_alert_level(product, message)
        
        # Create title
        title = f"Space Weather Alert: {product}"
        if alert_level:
            title = f"{alert_level} {title}"
        
        # Create summary
        summary = message
        
        # Add identity info to raw data
        raw_data = {
            "issue_datetime": issue_datetime,
            "product": product,
            "message": message,
            "link": link,
            "alert_level": alert_level,
        }
        
        return NewsItem(
            source=self.name,
            title=title,
            link=link or self.source_url,
            published_at=dt,
            summary=summary,
            raw=raw_data,
        )
    
    def _extract_alert_level(self, product: str, message: str) -> Optional[str]:
        """Extract alert level from product or message."""
        # Check for solar radiation storms
        s_match = re.search(r'S(\d) *\(', product) or re.search(r'S(\d) *\(', message)
        if s_match:
            level = int(s_match.group(1))
            return f"S{level}" if level > 2 else None
        
        # Check for geomagnetic storms
        g_match = re.search(r'G(\d) *\(', product) or re.search(r'G(\d) *\(', message)
        if g_match:
            level = int(g_match.group(1))
            return f"G{level}" if level > 2 else None
        
        # Check for radio blackouts
        r_match = re.search(r'R(\d) *\(', product) or re.search(r'R(\d) *\(', message)
        if r_match:
            level = int(r_match.group(1))
            return f"R{level}" if level > 2 else None
        
        # Check for X-class solar flares
        x_match = re.search(r'X(\d+(?:\.\d+)?) *flare', product, re.IGNORECASE) or re.search(r'X(\d+(?:\.\d+)?) *flare', message, re.IGNORECASE)
        if x_match:
            return f"X-class Solar Flare"
        
        # No significant alert level found
        return None
