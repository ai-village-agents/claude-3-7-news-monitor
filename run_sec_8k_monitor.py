#!/usr/bin/env python3
"""Script to run the SEC 8-K filings monitor."""

import os
import sys
import json
from datetime import datetime, timezone
import time

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.monitors.sec_8k_monitor import SEC8KMonitor
from scripts.monitors import NewsItem

def save_results(news_items):
    """Save the news items to a results file."""
    results_file = "sec_8k_results.txt"
    count = 0
    
    with open(results_file, "w") as f:
        for item in news_items:
            f.write(f"--- SEC 8-K Filing {count + 1} ---\n")
            f.write(f"Title: {item.title}\n")
            f.write(f"Source: {item.source}\n")
            f.write(f"Published: {item.published_at.isoformat()}\n")
            f.write(f"URL: {item.url}\n")
            f.write(f"Content:\n{item.content}\n\n")
            count += 1
    
    print(f"Found {count} SEC 8-K filings and saved to {results_file}")
    return count

def run_monitor():
    """Run the SEC 8-K monitor and save results."""
    print("Starting SEC 8-K filings monitor...")
    
    # Create and run the monitor
    monitor = SEC8KMonitor()
    news_items = list(monitor.run())
    
    # Save results to a file
    count = save_results(news_items)
    
    # Return the news items for further processing
    return news_items

if __name__ == "__main__":
    run_monitor()
