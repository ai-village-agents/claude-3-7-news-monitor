"""
Monitor for USGS Earthquake Data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests

from .news_monitor import Monitor, NewsItem

logger = logging.getLogger(__name__)


class USGSEarthquakeMonitor(Monitor):
    """
    Monitor that tracks significant earthquakes from the USGS Earthquake 
    Hazards Program feed.
    """

    name = "usgs-earthquakes"
    source_url = (
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_hour.geojson"
    )
    timeout = 30

    def parse(self, response: requests.Response) -> Iterable[NewsItem]:
        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Failed to decode USGS response as JSON: %s", exc)
            return []

        if not isinstance(data, dict):
            logger.error("Unexpected payload type from USGS feed: %s", type(data))
            return []

        features = data.get("features", [])
        for feature in features:
            item = self._earthquake_to_item(feature)
            if item:
                yield item
    
    def monitor_description(self) -> str:
        return (
            "Tracks significant earthquakes reported by the USGS Earthquake "
            "Hazards Program."
        )
    
    def item_identity(self, item: NewsItem) -> str:
        """Use earthquake ID for identity."""
        eq_id = item.raw.get("id")
        if eq_id:
            return f"{self.name}:{eq_id}"
        return super().item_identity(item)

    def _earthquake_to_item(self, feature: dict) -> Optional[NewsItem]:
        """Convert a USGS GeoJSON feature to a NewsItem."""
        try:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            
            if not properties or not geometry:
                return None
            
            # Extract basic info
            eq_id = feature.get("id")
            if not eq_id:
                return None
            
            magnitude = properties.get("mag")
            place = properties.get("place")
            time_ms = properties.get("time")
            url = properties.get("url")
            
            if not magnitude or not place or not time_ms or not url:
                return None
            
            # Parse time
            time_dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            
            # Generate title
            title = f"M{magnitude} Earthquake - {place}"
            
            # Generate summary
            summary_parts = []
            
            summary_parts.append(f"A magnitude {magnitude} earthquake occurred {place}.")
            
            # Add coordinates if available
            coords = geometry.get("coordinates")
            if coords and len(coords) >= 2:
                lat, lon = coords[1], coords[0]
                depth = coords[2] if len(coords) > 2 else None
                
                summary_parts.append(f"Location: {lat:.4f}°N, {lon:.4f}°E")
                if depth is not None:
                    summary_parts.append(f"Depth: {depth:.1f} km")
            
            # Add felt reports if available
            felt = properties.get("felt")
            if felt:
                summary_parts.append(f"Felt reports: {felt}")
            
            # Add alert level if available
            alert = properties.get("alert")
            if alert and alert.lower() != "none":
                summary_parts.append(f"Alert level: {alert.upper()}")
            
            # Add tsunami warning if present
            tsunami = properties.get("tsunami")
            if tsunami and tsunami == 1:
                summary_parts.append("**TSUNAMI WARNING ISSUED**")
            
            # Combine summary
            summary = " ".join(summary_parts)
            
            # Create NewsItem
            return NewsItem(
                source=self.name,
                title=title,
                link=url,
                published_at=time_dt,
                summary=summary,
                raw=feature,
            )
        
        except Exception as e:
            logger.error(f"Error processing earthquake data: {e}")
            return None
