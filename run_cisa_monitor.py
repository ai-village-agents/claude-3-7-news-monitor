#!/usr/bin/env python3

"""
Script to run the CISA Monitor and publish new findings.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Import the CISA monitor
sys.path.append(str(project_root / "scripts"))
from scripts.monitors.cisa_monitor import CISAMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("cisa_monitor")

def publish_news_item(item):
    """Publish a news item using the publish_story.sh script."""
    logger.info(f"Publishing: {item.title}")
    
    try:
        subprocess.run([
            str(project_root / "publish_story.sh"),
            item.title,
            item.content or "Breaking cybersecurity alert from CISA.",
            item.url
        ], check=True)
        logger.info(f"Successfully published: {item.title}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error publishing {item.title}: {e}")
        return False

def main():
    logger.info("Starting CISA monitor")
    
    # Initialize and run the monitor
    monitor = CISAMonitor()
    
    try:
        logger.info("Fetching data from CISA...")
        raw_data = monitor.fetch()
        
        logger.info("Parsing CISA data...")
        news_items = list(monitor.parse(raw_data))
        
        if not news_items:
            logger.info("No news items found from CISA")
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
            
            # If no breaking items, publish the 3 newest items
            recent_items = sorted(news_items, key=lambda x: x.date, reverse=True)[:3]
            
            if recent_items:
                logger.info(f"Publishing {len(recent_items)} most recent CISA items")
                for item in recent_items:
                    logger.info(f"Processing recent item: {item.title} - {item.source} - {item.date}")
                    publish_news_item(item)
    
    except Exception as e:
        logger.error(f"Error running CISA monitor: {e}")

if __name__ == "__main__":
    main()
