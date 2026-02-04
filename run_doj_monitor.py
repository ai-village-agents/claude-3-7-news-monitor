#!/usr/bin/env python3

"""
Script to run the DOJ Monitor and save results.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add the root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now import from scripts.monitors
from scripts.monitors.doj_monitor import DOJMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("doj_monitor")

def main():
    logger.info("Starting DOJ monitor")
    
    # Create and run the monitor
    monitor = DOJMonitor()
    raw_data = monitor.fetch()
    
    if not raw_data:
        logger.error("Failed to fetch data from DOJ website")
        return
    
    logger.info("Successfully fetched DOJ data")
    
    # Parse the data
    news_items = list(monitor.parse(raw_data))
    logger.info(f"Found {len(news_items)} DOJ press releases")
    
    # Filter for breaking news
    breaking_news = [item for item in news_items if monitor.check_if_breaking(item)]
    logger.info(f"Found {len(breaking_news)} breaking DOJ press releases")
    
    # Save results to file
    output_path = Path(__file__).parent.parent / "doj_results.txt"
    
    with open(output_path, "w") as f:
        for item in breaking_news:
            f.write(f"[DOJ] {item.date.strftime('%Y-%m-%d')} | {item.title}\n")
            f.write(f"Source: {item.source}\n")
            f.write(f"URL: {item.url}\n")
            f.write(f"{item.content}\n")
            f.write("-" * 80 + "\n\n")
    
    logger.info(f"Saved results to {output_path}")
    logger.info("DOJ monitor completed")

if __name__ == "__main__":
    main()
