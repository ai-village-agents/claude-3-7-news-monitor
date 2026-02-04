#!/usr/bin/env python3

"""
Script to run the International Courts Monitor and publish new findings.
Specifically designed for the 12:00 PM PT monitoring window.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Import the international courts monitor
sys.path.append(str(project_root / "scripts"))
from scripts.monitors.international_courts import InternationalCourtsMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("courts_monitor")

def publish_news_item(item):
    """Publish a news item using the publish_story.sh script."""
    logger.info(f"Publishing: {item.title}")
    
    try:
        subprocess.run([
            str(project_root / "publish_story.sh"),
            item.title,
            item.content or "Breaking news from international courts.",
            item.url
        ], check=True)
        logger.info(f"Successfully published: {item.title}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error publishing {item.title}: {e}")
        return False

def main():
    logger.info("Starting International Courts monitor")
    
    # Initialize and run the monitor
    monitor = InternationalCourtsMonitor()
    
    try:
        logger.info("Fetching data from international courts...")
        raw_data = monitor.fetch()
        
        logger.info("Parsing court data...")
        news_items = list(monitor.parse(raw_data))
        
        if not news_items:
            logger.info("No news items found from international courts")
            return
        
        logger.info(f"Found {len(news_items)} news items")
        
        # Filter for breaking news and today's items
        breaking_items = [item for item in news_items if monitor.check_if_breaking(item)]
        
        if breaking_items:
            logger.info(f"Found {len(breaking_items)} breaking news items from today")
            
            # Publish each breaking item
            for item in breaking_items:
                logger.info(f"Processing item: {item.title} - {item.source} - {item.date}")
                publish_news_item(item)
        else:
            logger.info("No breaking news items found from today")
            
            # If no breaking items, check for recent ones (last 3 days)
            today = datetime.now().date()
            recent_items = [
                item for item in news_items 
                if (today - item.date.date()).days <= 3
            ]
            
            if recent_items:
                logger.info(f"Found {len(recent_items)} recent items (last 3 days)")
                for item in recent_items[:5]:  # Publish up to 5 recent items
                    logger.info(f"Processing recent item: {item.title} - {item.source} - {item.date}")
                    publish_news_item(item)
    
    except Exception as e:
        logger.error(f"Error running international courts monitor: {e}")

if __name__ == "__main__":
    main()
