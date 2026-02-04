"""Monitor implementation for CISA (Cybersecurity & Infrastructure Security Agency)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional
import requests
from bs4 import BeautifulSoup

from . import Monitor, NewsItem


class CISAMonitor(Monitor):
    """Monitor that tracks CISA alerts and advisories."""

    CISA_ALERTS_URL = "https://www.cisa.gov/news-events/cybersecurity-advisories"
    KEV_CATALOG_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    
    SOURCE_CISA_ALERTS = "CISA Cybersecurity Advisories"
    SOURCE_CISA_KEV = "CISA Known Exploited Vulnerabilities"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def fetch(self) -> Dict:
        """Collect raw data from CISA sources."""
        
        return {
            "alerts": self._fetch_cisa_alerts(),
            "kev": self._fetch_kev_catalog(),
        }

    def parse(self, raw_data: Dict) -> Iterable[NewsItem]:
        """Parse all CISA data into news items."""
        
        raw_data = raw_data or {}
        
        def iter_items() -> Iterator[NewsItem]:
            yield from self._parse_cisa_alerts(raw_data.get("alerts", ""))
            yield from self._parse_kev_catalog(raw_data.get("kev", ""))
        
        return iter_items()

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Check if a news item is breaking news (published today)."""
        
        if not item.date:
            return False
            
        item_dt = item.date
        if item_dt.tzinfo is None:
            item_dt = item_dt.replace(tzinfo=timezone.utc)
            
        today_utc = datetime.now(timezone.utc).date()
        return item_dt.astimezone(timezone.utc).date() == today_utc
        
    def _fetch_cisa_alerts(self) -> str:
        """Fetch CISA alerts page."""
        
        try:
            response = self.session.get(self.CISA_ALERTS_URL, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""
            
    def _fetch_kev_catalog(self) -> str:
        """Fetch CISA KEV catalog JSON."""
        
        try:
            response = self.session.get(self.KEV_CATALOG_URL, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""
            
    def _parse_cisa_alerts(self, html_content: str) -> Iterator[NewsItem]:
        """Parse CISA alerts from HTML."""
        
        if not html_content:
            return iter(())
            
        soup = BeautifulSoup(html_content, "html.parser")
        alerts = soup.select("article.usa-card, div.views-row")
        
        for alert in alerts:
            try:
                title_elem = alert.select_one("h3.usa-card__heading, h2 a")
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                
                # Get URL
                url = ""
                link = alert.select_one("a[href]")
                if link:
                    url = link.get("href", "")
                    if url and not url.startswith(("http://", "https://")):
                        url = "https://www.cisa.gov" + url
                        
                # Get date
                date_elem = alert.select_one("time, span.datetime, div.date-display-single")
                date_str = date_elem.get_text(strip=True) if date_elem else ""
                
                date = None
                if date_str:
                    try:
                        # Try different date formats
                        for fmt in ["%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                            try:
                                date = datetime.strptime(date_str, fmt)
                                date = date.replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        date = datetime.now(timezone.utc)
                else:
                    date = datetime.now(timezone.utc)
                    
                # Get summary
                summary_elem = alert.select_one("p, div.usa-card__body")
                summary = summary_elem.get_text(strip=True) if summary_elem else ""
                
                yield NewsItem(
                    title=title,
                    source=self.SOURCE_CISA_ALERTS,
                    url=url,
                    date=date,
                    content=summary,
                )
            except Exception:
                continue
                
    def _parse_kev_catalog(self, json_content: str) -> Iterator[NewsItem]:
        """Parse CISA KEV catalog from JSON."""
        
        if not json_content:
            return iter(())
            
        try:
            data = json.loads(json_content)
            vulnerabilities = data.get("vulnerabilities", [])
            
            # Sort by date added (newest first)
            vulnerabilities.sort(
                key=lambda x: x.get("dateAdded", ""), reverse=True
            )
            
            # Process each vulnerability
            for vuln in vulnerabilities[:20]:  # Limit to newest 20
                try:
                    cve_id = vuln.get("cveID", "")
                    vendor = vuln.get("vendorProject", "")
                    product = vuln.get("product", "")
                    
                    title = f"CISA KEV: {cve_id} - {vendor} {product} Vulnerability"
                    
                    date_added_str = vuln.get("dateAdded", "")
                    date_added = None
                    if date_added_str:
                        try:
                            date_added = datetime.strptime(date_added_str, "%Y-%m-%d")
                            date_added = date_added.replace(tzinfo=timezone.utc)
                        except ValueError:
                            date_added = datetime.now(timezone.utc)
                    
                    description = vuln.get("shortDescription", "")
                    
                    yield NewsItem(
                        title=title,
                        source=self.SOURCE_CISA_KEV,
                        url=f"https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                        date=date_added,
                        content=f"CVE: {cve_id}\nVendor: {vendor}\nProduct: {product}\nDescription: {description}",
                    )
                except Exception:
                    continue
        except Exception:
            return iter(())
