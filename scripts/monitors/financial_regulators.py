"""Monitor implementation for financial regulators (SEC, CFTC, NASDAQ, etc.)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Dict, Any, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import Monitor, NewsItem


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class FinancialRegulatorsMonitor(Monitor):
    """Monitor that scrapes financial regulatory websites for news and releases."""

    REGULATORS = {
        "SEC": {
            "base_url": "https://www.sec.gov",
            "news_url": "https://www.sec.gov/news/pressreleases",
            "source": "U.S. Securities and Exchange Commission (SEC)"
        },
        "CFTC": {
            "base_url": "https://www.cftc.gov",
            "news_url": "https://www.cftc.gov/PressRoom/PressReleases/index.htm",
            "source": "Commodity Futures Trading Commission (CFTC)"
        },
        "NASDAQ": {
            "base_url": "https://www.nasdaqtrader.com",
            "news_url": "https://www.nasdaqtrader.com/Trader.aspx?id=TraderNews",
            "source": "NASDAQ"
        },
        "FINRA": {
            "base_url": "https://www.finra.org",
            "news_url": "https://www.finra.org/media-center/newsreleases",
            "source": "Financial Industry Regulatory Authority (FINRA)"
        }
    }

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        # Standard browser user-agent helps avoid regulator site blocks
        self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

    def fetch(self) -> Dict[str, str]:
        """Retrieve HTML pages from all financial regulator websites."""
        results = {}
        
        for regulator_id, regulator_info in self.REGULATORS.items():
            try:
                response = self.session.get(
                    regulator_info["news_url"],
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    timeout=15,
                )
                response.raise_for_status()
                results[regulator_id] = response.text
            except Exception as e:
                print(f"Error fetching {regulator_id} data: {e}")
                results[regulator_id] = ""
                
        return results

    def parse(self, raw_data: Dict[str, str]) -> Iterable[NewsItem]:
        """Parse all regulator websites HTML into `NewsItem` instances."""
        
        all_items = []
        
        # Process each regulator's data
        for regulator_id, html in raw_data.items():
            if not html:
                continue
                
            regulator_info = self.REGULATORS[regulator_id]
            
            # Use the appropriate parsing method based on regulator
            parser_method = getattr(self, f"_parse_{regulator_id.lower()}", None)
            if parser_method:
                items = list(parser_method(html, regulator_info))
                all_items.extend(items)
            
        return all_items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag items published today as breaking news."""
        
        item_date = item.date
        if item_date.tzinfo is None:
            item_date = item_date.replace(tzinfo=timezone.utc)

        today_utc = datetime.now(timezone.utc).date()
        return item_date.astimezone(timezone.utc).date() == today_utc

    def _parse_sec(self, html: str, regulator_info: Dict[str, str]) -> Iterator[NewsItem]:
        """Parse SEC website content."""
        soup = BeautifulSoup(html, "html.parser")
        
        for item in soup.select(".press-releases .pr-list-page-row"):
            try:
                # Extract title and link
                title_element = item.select_one("a")
                if not title_element:
                    continue
                    
                title = title_element.get_text(strip=True)
                if not title:
                    continue
                    
                href = title_element.get("href", "")
                url = urljoin(regulator_info["base_url"], href)
                
                # Extract date
                date_element = item.select_one(".pr-list-date")
                date_str = date_element.get_text(strip=True) if date_element else None
                date = self._parse_date(date_str) or datetime.now(timezone.utc)
                
                # Use the title as content since SEC doesn't show summaries
                content = title
                
                yield NewsItem(
                    title=title,
                    source=regulator_info["source"],
                    url=url,
                    date=date,
                    content=content,
                )
            except Exception as e:
                print(f"Error parsing SEC item: {e}")

    def _parse_cftc(self, html: str, regulator_info: Dict[str, str]) -> Iterator[NewsItem]:
        """Parse CFTC website content."""
        soup = BeautifulSoup(html, "html.parser")
        
        for item in soup.select(".views-row"):
            try:
                # Extract title and link
                title_element = item.select_one(".cftc-list-title a")
                if not title_element:
                    continue
                    
                title = title_element.get_text(strip=True)
                if not title:
                    continue
                    
                href = title_element.get("href", "")
                url = urljoin(regulator_info["base_url"], href)
                
                # Extract date
                date_element = item.select_one(".date-display-single")
                date_str = date_element.get_text(strip=True) if date_element else None
                date = self._parse_date(date_str) or datetime.now(timezone.utc)
                
                # Extract release number as additional info
                release_num = item.select_one(".cftc-list-num")
                content = ""
                if release_num:
                    content = f"Release Number: {release_num.get_text(strip=True)}"
                
                yield NewsItem(
                    title=title,
                    source=regulator_info["source"],
                    url=url,
                    date=date,
                    content=content,
                )
            except Exception as e:
                print(f"Error parsing CFTC item: {e}")

    def _parse_nasdaq(self, html: str, regulator_info: Dict[str, str]) -> Iterator[NewsItem]:
        """Parse NASDAQ trader news content."""
        soup = BeautifulSoup(html, "html.parser")
        
        for item in soup.select("#ctl00_ctl00_ContentPlaceHolder_Main_ContentPlaceHolder_Results_Results tr"):
            try:
                # Skip header row
                if item.select_one("th"):
                    continue
                
                cells = item.select("td")
                if len(cells) < 3:
                    continue
                
                # Extract date (first column)
                date_cell = cells[0]
                date_str = date_cell.get_text(strip=True)
                date = self._parse_date(date_str) or datetime.now(timezone.utc)
                
                # Extract title and link (second column)
                title_element = cells[1].select_one("a")
                if not title_element:
                    continue
                    
                title = title_element.get_text(strip=True)
                if not title:
                    continue
                
                href = title_element.get("href", "")
                url = urljoin(regulator_info["base_url"], href)
                
                # Get category from third column
                category = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                content = f"Category: {category}" if category else ""
                
                yield NewsItem(
                    title=title,
                    source=regulator_info["source"],
                    url=url,
                    date=date,
                    content=content,
                )
            except Exception as e:
                print(f"Error parsing NASDAQ item: {e}")

    def _parse_finra(self, html: str, regulator_info: Dict[str, str]) -> Iterator[NewsItem]:
        """Parse FINRA website content."""
        soup = BeautifulSoup(html, "html.parser")
        
        for item in soup.select(".finra-listing-result"):
            try:
                # Extract title and link
                title_element = item.select_one("h3.title a")
                if not title_element:
                    continue
                    
                title = title_element.get_text(strip=True)
                if not title:
                    continue
                    
                href = title_element.get("href", "")
                url = urljoin(regulator_info["base_url"], href)
                
                # Extract date
                date_element = item.select_one(".date")
                date_str = date_element.get_text(strip=True) if date_element else None
                date = self._parse_date(date_str) or datetime.now(timezone.utc)
                
                # Extract content
                content_element = item.select_one(".summary")
                content = content_element.get_text(" ", strip=True) if content_element else ""
                
                yield NewsItem(
                    title=title,
                    source=regulator_info["source"],
                    url=url,
                    date=date,
                    content=content,
                )
            except Exception as e:
                print(f"Error parsing FINRA item: {e}")

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date strings from various financial regulator websites into UTC datetimes."""
        if not date_str:
            return None

        # Clean up the date string
        date_str = date_str.strip()
        
        # Try common date formats used by financial regulators
        formats = [
            "%m/%d/%Y",      # MM/DD/YYYY (US format)
            "%Y-%m-%d",      # YYYY-MM-DD
            "%B %d, %Y",     # Month DD, YYYY
            "%b %d, %Y",     # Abbreviated Month DD, YYYY
            "%d %B %Y",      # DD Month YYYY
            "%d-%b-%Y",      # DD-Mon-YYYY
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
                
        # Try ISO format as a fallback
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


__all__ = ["FinancialRegulatorsMonitor"]
