#!/usr/bin/env python3

"""
Updated main script to run all monitors including new undermonitored sources
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Import all monitors
from src.monitors.cisa_kev_monitor import CisaKevMonitor
from src.monitors.usgs_monitor import USGSEarthquakeMonitor
from src.monitors.noaa_swpc_monitor import NOAASWPCMonitor
from src.monitors.sec_edgar_monitor import SECEdgarMonitor
# Import new monitors
from src.monitors.treasury_ofac_monitor import TreasuryOFACMonitor
from src.monitors.doj_monitor import DOJMonitor
from src.monitors.eu_commission_monitor import EUCommissionMonitor
from src.monitors.fcc_monitor import FCCMonitor

from src.monitors.news_monitor import Monitor, NewsItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("monitor_runner")

DOCS_DIR = project_root / "docs"

def run_monitor(monitor: Monitor, timeout: int = 60) -> List[tuple]:
    """Run a monitor and generate articles for new items with timeout protection"""
    logger.info(f"Running monitor: {monitor.name} with timeout {timeout} seconds")
    
    try:
        # Set up timeout handling
        import signal
        from contextlib import contextmanager
        
        @contextmanager
        def timeout_context(seconds):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Monitor timed out after {seconds} seconds")
            
            # Set the timeout handler
            original_handler = signal.signal(signal.SIGALRM, timeout_handler)
            # Set the timeout
            signal.alarm(seconds)
            try:
                yield
            finally:
                # Reset the alarm and restore the original handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, original_handler)
        
        # Run the monitor with timeout
        with timeout_context(timeout):
            # Run the monitor
            new_items = monitor.run_once()
            
            if not new_items:
                logger.info(f"No new items found for {monitor.name}")
                return []
            
            logger.info(f"Found {len(new_items)} new items for {monitor.name}")
            
            # Generate articles for each item
            articles = []
            for item in new_items:
                try:
                    # Use the updated generate_article_fixed.py script
                    article_path = Path(DOCS_DIR / f"{item.source}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
                    article_path.mkdir(exist_ok=True, parents=True)
                    
                    # Create an HTML file in the article directory
                    article_file = article_path / "index.html"
                    
                    # Call the article generator script
                    subprocess.run([
                        "python3", 
                        str(project_root / "src" / "generate_article_fixed.py"),
                        item.title,
                        item.summary,
                        item.link
                    ], check=True)
                    
                    articles.append((item.title, item.source, article_path))
                except Exception as e:
                    logger.error(f"Error creating article for {item.title}: {e}")
            
            return articles
    
    except TimeoutError as e:
        logger.error(f"Monitor {monitor.name} timed out: {e}")
        return []
    except Exception as e:
        logger.error(f"Error running {monitor.name} monitor: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Run news monitors and publish findings")
    parser.add_argument("--no-git", action="store_true", help="Skip git operations")
    parser.add_argument(
        "--monitor", 
        choices=["all", "cisa", "usgs", "noaa", "sec", "treasury", "doj", "eu", "fcc", "undermonitored"], 
        default="all", 
        help="Specify which monitor(s) to run"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for each monitor (default: 60)"
    )
    args = parser.parse_args()
    
    # Initialize monitors based on arguments
    monitors = []
    
    if args.monitor in ["all", "cisa"]:
        monitors.append(CisaKevMonitor())
    if args.monitor in ["all", "usgs"]:
        monitors.append(USGSEarthquakeMonitor())
    if args.monitor in ["all", "noaa"]:
        monitors.append(NOAASWPCMonitor())
    if args.monitor in ["all", "sec"]:
        monitors.append(SECEdgarMonitor())
    # Add new undermonitored sources
    if args.monitor in ["all", "treasury", "undermonitored"]:
        monitors.append(TreasuryOFACMonitor())
    if args.monitor in ["all", "doj", "undermonitored"]:
        monitors.append(DOJMonitor())
    if args.monitor in ["all", "eu", "undermonitored"]:
        monitors.append(EUCommissionMonitor())
    if args.monitor in ["all", "fcc", "undermonitored"]:
        monitors.append(FCCMonitor())
    
    # Run all monitors
    all_articles = []
    for monitor in monitors:
        articles = run_monitor(monitor, args.timeout)
        all_articles.extend(articles)
    
    # Update index and publish if we have new articles
    if all_articles:
        logger.info(f"Generated {len(all_articles)} articles")
        
        # Commit and push changes
        if not args.no_git:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Add {len(all_articles)} new articles from {', '.join(m.name for m in monitors)} - {timestamp}"
            subprocess.run(["git", "add", "."], cwd=project_root, check=True)
            subprocess.run(["git", "commit", "-m", message], cwd=project_root, check=True)
            subprocess.run(["git", "push"], cwd=project_root, check=True)
            logger.info(f"Successfully published changes: {message}")
    else:
        logger.info("No new articles to publish")

if __name__ == "__main__":
    main()
