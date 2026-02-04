"""Monitor implementation for CISA Known Exploited Vulnerabilities (KEV) Catalog."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Iterable, Iterator, Optional, Dict, Any, List
import json
import re

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


class CISAKEVMonitor(Monitor):
    """Monitor that tracks CISA Known Exploited Vulnerabilities (KEV) Catalog."""

    KEV_JSON_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    KEV_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
    SOURCE = "CISA Known Exploited Vulnerabilities (KEV) Catalog"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        # Set a descriptive user-agent
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, Any]:
        """Retrieve the KEV catalog JSON data."""
        try:
            response = self.session.get(
                self.KEV_JSON_URL,
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching CISA KEV data: {e}")
            return {}

    def parse(self, raw_data: Dict[str, Any]) -> Iterable[NewsItem]:
        """Parse the KEV catalog JSON into `NewsItem` instances."""
        if not raw_data or 'vulnerabilities' not in raw_data:
            return []

        vulnerabilities = raw_data.get('vulnerabilities', [])
        
        def iter_items() -> Iterator[NewsItem]:
            for vuln in vulnerabilities:
                try:
                    # Extract CVE ID as title basis
                    cve_id = vuln.get('cveID')
                    if not cve_id:
                        continue
                    
                    # Get vulnerability name/description
                    vuln_name = vuln.get('vulnerabilityName', '')
                    
                    # Create a meaningful title
                    title = f"CISA KEV Alert: {cve_id} - {vuln_name}"
                    
                    # Build content with all relevant details
                    content_parts = []
                    
                    vendor = vuln.get('vendorProject', '')
                    product = vuln.get('product', '')
                    if vendor and product:
                        content_parts.append(f"Affected: {vendor} {product}")
                    
                    vuln_description = vuln.get('shortDescription', '')
                    if vuln_description:
                        content_parts.append(f"Description: {vuln_description}")
                        
                    required_action = vuln.get('requiredAction', '')
                    if required_action:
                        content_parts.append(f"Required Action: {required_action}")
                        
                    due_date = vuln.get('dueDate', '')
                    if due_date:
                        content_parts.append(f"Due Date: {due_date}")
                    
                    # Join all parts with line breaks
                    content = "\n".join(content_parts)
                    
                    # Construct a URL to the catalog filtered for this CVE
                    url = f"{self.KEV_CATALOG_URL}?cveCode={cve_id}"
                    
                    # Parse date added (critical for determining if breaking)
                    date_added = vuln.get('dateAdded', '')
                    date = self._parse_date(date_added) or datetime.now(timezone.utc)
                    
                    yield NewsItem(
                        title=title,
                        source=self.SOURCE,
                        url=url,
                        date=date,
                        content=content,
                    )
                except Exception as e:
                    print(f"Error parsing CISA KEV vulnerability: {e}")
        
        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items added within the past day as breaking news.
        
        CISA KEVs are always critical, so we consider them breaking
        if added within the past 24 hours rather than just today.
        """
        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        return item_date >= one_day_ago

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse CISA date format into UTC datetime."""
        if not date_str:
            return None

        # CISA uses YYYY/MM/DD format
        try:
            dt = datetime.strptime(date_str, "%Y/%m/%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
            
        # Try alternative formats as fallback
        for fmt in ["%Y-%m-%d", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
                
        return None


__all__ = ["CISAKEVMonitor"]
