"""Monitor implementation for Federal Register documents."""

from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
import json

import requests

from . import Monitor, NewsItem


class FederalRegisterMonitor(Monitor):
    """Monitor that fetches documents from the Federal Register API."""

    BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"
    SOURCE = "Federal Register"
    
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, Any]:
        """Retrieve documents from the Federal Register API."""
        
        # Get today's date and format as YYYY-MM-DD
        today = date.today()
        
        # Parameters for the API request
        params = {
            "conditions[publication_date]": today.isoformat(),
            "per_page": 100,  # Maximum per page
            "order": "newest"
        }
        
        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching Federal Register data: {e}")
            return {"results": [], "count": 0}

    def parse(self, raw_data: Dict[str, Any]) -> Iterable[NewsItem]:
        """Parse the Federal Register API response into NewsItem instances."""
        
        results = raw_data.get("results", [])
        items: List[NewsItem] = []
        
        for document in results:
            try:
                document_number = document.get("document_number", "")
                title = document.get("title", "")
                
                if not title:
                    continue
                
                # Get the html_url or generate a fallback URL
                url = document.get("html_url", "")
                if not url and document_number:
                    url = f"https://www.federalregister.gov/documents/{document_number}"
                
                # Get publication date
                pub_date_str = document.get("publication_date")
                if not pub_date_str:
                    continue
                
                try:
                    pub_date = datetime.fromisoformat(pub_date_str)
                except ValueError:
                    # Handle alternative date format
                    try:
                        pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
                    except ValueError:
                        continue
                
                # Add timezone info
                pub_date = pub_date.replace(tzinfo=timezone.utc)
                
                # Get abstract or generate content from other fields
                abstract = document.get("abstract", "")
                if not abstract:
                    agency_name = document.get("agencies", [{}])[0].get("name", "")
                    doc_type = document.get("type", "")
                    content = f"Federal Register document from {agency_name if agency_name else 'an agency'}"
                    if doc_type:
                        content += f" ({doc_type})"
                else:
                    content = abstract
                
                items.append(
                    NewsItem(
                        title=title,
                        source=self.SOURCE,
                        url=url,
                        date=pub_date,
                        content=content,
                    )
                )
                
            except Exception as e:
                print(f"Error parsing Federal Register document: {e}")
                continue
            
        return items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag recent Federal Register documents as breaking."""
        
        # All documents published today are considered breaking news
        now = datetime.now(timezone.utc)
        is_today = item.date.date() == now.date()
        
        return is_today


__all__ = ["FederalRegisterMonitor"]
