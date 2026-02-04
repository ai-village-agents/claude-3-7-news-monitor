"""Monitor implementation for USGS earthquake data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

from . import Monitor, NewsItem


class USGSEarthquakeMonitor(Monitor):
    """Monitor that fetches earthquake data from USGS API."""

    BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    SOURCE = "USGS Earthquakes"
    
    # Magnitude threshold for breaking news
    MAGNITUDE_THRESHOLD = 4.5

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "claude-news-monitor/1.0 (+https://ai-village-agents.github.io/claude-3-7-news-monitor/)",
        )

    def fetch(self) -> Dict[str, Any]:
        """Retrieve the USGS earthquake feed as JSON."""
        
        try:
            response = self.session.get(
                self.BASE_URL,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching USGS earthquake data: {e}")
            return {"features": []}

    def parse(self, raw_data: Dict[str, Any]) -> Iterable[NewsItem]:
        """Parse the USGS GeoJSON into NewsItem instances."""
        
        features = raw_data.get("features", [])
        items: List[NewsItem] = []
        
        for feature in features:
            props = feature.get("properties", {})
            
            magnitude = props.get("mag")
            if magnitude is None:
                continue
                
            place = props.get("place", "Unknown location")
            title = f"Magnitude {magnitude} Earthquake - {place}"
            
            # Get the detail URL or use the USGS homepage
            url = props.get("url", "https://earthquake.usgs.gov/")
            
            # Get the time (milliseconds since epoch)
            time_ms = props.get("time")
            if time_ms is None:
                continue
                
            # Convert to datetime
            quake_time = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)
            
            # Build content with details
            content_parts = [
                f"Magnitude: {magnitude}",
                f"Location: {place}",
                f"Depth: {props.get('depth', 'Unknown')} km",
                f"Time: {quake_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            ]
            
            if props.get("tsunami") == 1:
                content_parts.append("Tsunami: Warning issued")
                
            content = " | ".join(content_parts)
            
            items.append(
                NewsItem(
                    title=title,
                    source=self.SOURCE,
                    url=url,
                    date=quake_time,
                    content=content,
                )
            )
            
        return items

    def check_if_breaking(self, item: NewsItem) -> bool:
        """Flag significant and recent earthquakes as breaking news."""
        
        # Extract magnitude from title
        try:
            magnitude_str = item.title.split("Magnitude ")[1].split(" ")[0]
            magnitude = float(magnitude_str)
        except (IndexError, ValueError):
            magnitude = 0.0
        
        # Check if it's recent (within the last hour)
        now = datetime.now(timezone.utc)
        is_recent = (now - item.date) <= timedelta(hours=1)
        
        # Check if it meets the magnitude threshold
        is_significant = magnitude >= self.MAGNITUDE_THRESHOLD
        
        return is_recent and is_significant


__all__ = ["USGSEarthquakeMonitor"]
