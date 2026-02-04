"""Monitor implementation for SEC 8-K filings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Dict, Any, List
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from . import Monitor, NewsItem

class SEC8KMonitor(Monitor):
    """Monitor that fetches SEC 8-K filings (material events) from EDGAR database."""

    # SEC EDGAR URLs
    BASE_URL = "https://www.sec.gov"
    EDGAR_SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
    
    # User agent is required for SEC EDGAR API
    HEADERS = {
        "User-Agent": "Claude-3-7-News-Monitor claude-3.7@agentvillage.org",
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }
    
    # Material events of particular interest (item numbers in 8-K filings)
    MATERIAL_EVENTS = {
        "Item 1.01": "Entry into a Material Agreement",
        "Item 1.02": "Termination of a Material Agreement",
        "Item 2.01": "Completion of Acquisition or Disposition",
        "Item 2.02": "Results of Operations and Financial Condition",
        "Item 2.03": "Creation of a Direct Financial Obligation",
        "Item 2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
        "Item 2.05": "Costs Associated with Exit or Disposal Activities",
        "Item 2.06": "Material Impairments",
        "Item 3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
        "Item 3.03": "Material Modification to Rights of Security Holders",
        "Item 4.01": "Changes in Registrant's Certifying Accountant",
        "Item 4.02": "Non-Reliance on Previously Issued Financial Statements",
        "Item 5.01": "Changes in Control of Registrant",
        "Item 5.02": "Departure of Directors or Certain Officers",
        "Item 5.03": "Amendments to Articles of Incorporation or Bylaws",
        "Item 5.08": "Shareholder Director Nominations",
        "Item 7.01": "Regulation FD Disclosure",
        "Item 8.01": "Other Events",
    }

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        """Initialize with a requests session."""
        self.session = session or requests.Session()
        for header, value in self.HEADERS.items():
            self.session.headers.update({header: value})

    def fetch(self) -> Dict[str, Any]:
        """Fetch recent 8-K filings from SEC EDGAR database."""
        try:
            # Get today's date (Feb 4, 2026)
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            
            # Search for 8-K filings from today
            params = {
                "action": "getcurrent",
                "owner": "include",
                "type": "8-K",
                "count": "100",
                "dateb": today
            }
            
            # SEC rate limits to 10 requests per second
            time.sleep(0.1)
            
            response = self.session.get(self.EDGAR_SEARCH_URL, params=params)
            response.raise_for_status()
            
            return {"html": response.text, "url": response.url}
        except requests.RequestException as e:
            print(f"Error fetching SEC 8-K filings: {e}")
            return {"html": "", "url": ""}

    def parse(self, data: Dict[str, Any]) -> Iterator[NewsItem]:
        """Parse SEC 8-K filings data and yield NewsItems."""
        if not data["html"]:
            return
        
        soup = BeautifulSoup(data["html"], "html.parser")
        
        # Find the table containing filing information
        table = soup.find("table", class_="tableFile2")
        if not table:
            return
        
        # Process each row in the table (each row is a filing)
        rows = table.find_all("tr")
        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                
                # Extract filing details
                filing_type = cells[0].text.strip()
                if not filing_type.startswith("8-K"):
                    continue
                
                company_name = cells[1].text.strip()
                filing_date_str = cells[3].text.strip()
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                
                # Only process filings from today (Feb 4, 2026)
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                if filing_date < today:
                    continue
                
                # Get the filing detail page URL
                detail_link = cells[1].find("a")
                if not detail_link:
                    continue
                    
                detail_href = detail_link.get("href", "")
                if not detail_href:
                    continue
                
                detail_url = f"{self.BASE_URL}{detail_href}"
                
                # Fetch and parse the filing detail page to extract material events
                time.sleep(0.1)  # SEC rate limit compliance
                detail_response = self.session.get(detail_url)
                detail_response.raise_for_status()
                
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                
                # Get the actual 8-K document URL
                filing_table = detail_soup.find("table", class_="tableFile")
                if not filing_table:
                    continue
                
                document_links = filing_table.find_all("a")
                filing_url = None
                for link in document_links:
                    if "8-K" in link.text and ".htm" in link.get("href", ""):
                        filing_url = f"{self.BASE_URL}{link.get('href')}"
                        break
                
                if not filing_url:
                    continue
                
                # Fetch and parse the 8-K document
                time.sleep(0.1)  # SEC rate limit compliance
                filing_response = self.session.get(filing_url)
                filing_response.raise_for_status()
                
                filing_soup = BeautifulSoup(filing_response.text, "html.parser")
                
                # Extract material events from the filing
                material_events = []
                for item, description in self.MATERIAL_EVENTS.items():
                    if item in filing_response.text:
                        material_events.append(f"{item} - {description}")
                
                if not material_events:
                    continue
                
                # Extract the filing summary/description
                filing_text = filing_soup.get_text()
                summary = self._extract_summary(filing_text)
                
                # Create a NewsItem
                news_item = NewsItem(
                    title=f"SEC 8-K Filing: {company_name} Reports {', '.join(material_events[:2])}",
                    content=f"Company: {company_name}\n\nFiling Type: {filing_type}\n\nMaterial Events: {', '.join(material_events)}\n\nSummary: {summary}\n\nFull details available on the SEC EDGAR database.",
                    source="U.S. Securities and Exchange Commission (SEC)",
                    url=filing_url,
                    published_at=filing_date
                )
                
                yield news_item
                
            except Exception as e:
                print(f"Error processing SEC 8-K filing row: {e}")
                continue
    
    def _extract_summary(self, text: str) -> str:
        """Extract a summary from the 8-K filing text."""
        # Look for common sections that contain useful summary information
        patterns = [
            r"Item\s+[78]\.01.*?([^\.]+\.[^\.]+\.)",
            r"ITEM\s+[78]\.01.*?([^\.]+\.[^\.]+\.)",
            r"pursuant to Item [78]\.01.*?([^\.]+\.[^\.]+\.)",
            r"The information in this[^\.]+\.([^\.]+\.)",
        ]
        
        for pattern in patterns:
            matches = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                return matches.group(1).strip()
        
        # If no specific section found, return a generic summary
        return "Material event reported. See SEC filing for details."
    
    def run(self) -> Iterable[NewsItem]:
        """Run the SEC 8-K monitor to fetch and process filings."""
        data = self.fetch()
        yield from self.parse(data)
