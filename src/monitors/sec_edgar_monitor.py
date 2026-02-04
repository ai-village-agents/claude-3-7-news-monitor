"""
Monitor for SEC EDGAR filings with a focus on major transactions.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable, Optional, Dict, Any

import requests
import feedparser

from .news_monitor import Monitor, NewsItem

logger = logging.getLogger(__name__)


class SECEdgarMonitor(Monitor):
    """
    Monitor that tracks significant filings in the SEC EDGAR database, with a
    focus on identifying major M&A activity, bankruptcies, and other
    high-impact corporate events.
    """

    name = "sec-edgar"
    source_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&start=0&count=40&output=atom"
    timeout = 30
    
    # List of form types to prioritize for high-impact events
    HIGH_PRIORITY_FORMS = {
        "8-K": "Material corporate event",
        "SC 13D": "Acquisition of 5%+ stake",
        "SC TO-C": "Written communication regarding takeover",
        "DEFM14A": "Definitive proxy for merger",
        "425": "Filing under Securities Act Rule 425",
        "S-4": "Registration for business combinations",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a session with appropriate headers for SEC.gov."""
        session = super()._create_session()
        session.headers.update({
            "User-Agent": "claude-3-7-news-monitor/1.0 claude-3-7@agentvillage.org",
            "Accept": "application/atom+xml, application/rss+xml, text/xml",
        })
        return session

    def parse(self, response: requests.Response) -> Iterable[NewsItem]:
        feed = feedparser.parse(response.content)
        
        for entry in feed.entries:
            try:
                item = self._process_filing_entry(entry)
                if item:
                    yield item
            except Exception as e:
                logger.error(f"Error processing SEC filing: {e}")
    
    def monitor_description(self) -> str:
        return (
            "Monitors the SEC EDGAR database for significant corporate filings "
            "including major M&A activity, bankruptcies, and other high-impact events."
        )
    
    def _process_filing_entry(self, entry: Dict[str, Any]) -> Optional[NewsItem]:
        """Process an individual filing entry from the SEC feed."""
        # Extract basic filing info
        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        
        if not title or not link:
            return None
        
        # Extract filing information
        company, form_type, rest = self._parse_filing_title(title)
        if not company or not form_type:
            return None
        
        # Check if this is a high-priority form
        if form_type not in self.HIGH_PRIORITY_FORMS:
            # Skip forms that aren't likely to be major news
            return None
        
        # Parse date
        pub_date = self._resolve_entry_datetime(entry)
        
        # Attempt to identify significant events
        event_type, confidence = self._identify_event_type(title, form_type, rest)
        if confidence < 0.7:
            # Skip events that we're not confident are significant
            return None
        
        # Create NewsItem title
        item_title = f"{company} - {event_type} - SEC Form {form_type}"
        
        # Create summary
        summary_parts = []
        summary_parts.append(f"{company} has filed an SEC Form {form_type} ({self.HIGH_PRIORITY_FORMS.get(form_type, '')}).")
        summary_parts.append(f"Event type: {event_type}")
        if rest:
            summary_parts.append(f"Filing details: {rest}")
        
        summary = " ".join(summary_parts)
        
        # Create raw data
        raw_data = {
            "company": company,
            "form_type": form_type,
            "details": rest,
            "event_type": event_type,
            "confidence": confidence,
            "title": title,
            "link": link,
        }
        
        return NewsItem(
            source=self.name,
            title=item_title,
            link=link,
            published_at=pub_date,
            summary=summary,
            raw=raw_data,
        )
    
    def _parse_filing_title(self, title: str) -> tuple[str, str, str]:
        """Parse a filing title into company, form type, and additional info."""
        # Expected format: "Company Name - Form Type - Additional Info"
        parts = title.split(" - ", 2)
        
        company = parts[0] if len(parts) > 0 else ""
        form_type = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""
        
        return company, form_type, rest
    
    def _identify_event_type(self, title: str, form_type: str, details: str) -> tuple[str, float]:
        """
        Identify the type of event from the filing details.
        Returns an event type and confidence score (0.0-1.0).
        """
        title_lower = title.lower()
        details_lower = details.lower()
        
        # Check for mergers and acquisitions
        if form_type in ["DEFM14A", "S-4"] or any(term in title_lower or term in details_lower for term in ["merger", "acquisition", "acquire"]):
            return "Merger/Acquisition", 0.9
        
        # Check for bankruptcy
        if "bankruptcy" in title_lower or "bankruptcy" in details_lower:
            return "Bankruptcy Filing", 0.95
        
        # Check for major stake acquisition
        if form_type == "SC 13D" or any(term in title_lower or term in details_lower for term in ["stake", "acquisition of shares"]):
            return "Significant Stake Acquisition", 0.85
        
        # Check for CEO/leadership changes
        if any(term in title_lower or term in details_lower for term in ["ceo", "chief executive", "executive change", "leadership"]):
            return "Leadership Change", 0.8
        
        # Check for financial distress
        if any(term in title_lower or term in details_lower for term in ["default", "debt", "restructuring"]):
            return "Financial Restructuring", 0.75
        
        # Check for major business announcements
        if any(term in title_lower or term in details_lower for term in ["agreement", "contract", "partnership"]):
            return "Major Business Agreement", 0.7
        
        # Default to a generic material event
        return "Material Corporate Event", 0.6
