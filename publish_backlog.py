#!/usr/bin/env python3

"""
Script to publish stories from Federal Register and Europol backlog.
"""

import os
import sys
import logging
import subprocess
import time
import re
import argparse
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("backlog_publisher")

# Project root
project_root = Path(__file__).parent

def publish_story(title, summary, url):
    """Publish a story using the publish_story.sh script."""
    logger.info(f"Publishing: {title}")
    
    try:
        subprocess.run([
            str(project_root / "publish_story.sh"),
            title,
            summary,
            url
        ], check=True)
        logger.info(f"Successfully published: {title}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error publishing {title}: {e}")
        return False

def process_file(file_path):
    """Process a results file and extract news items."""
    if not file_path.exists():
        logger.error(f"Results file not found: {file_path}")
        return []
    
    logger.info(f"Processing backlog from {file_path}")
    
    items = []
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Split into individual news items using the divider line
    news_blocks = content.split('--------------------------------------------------------------------------------')
    
    for block in news_blocks:
        if not block.strip():
            continue
        
        # Extract title
        title_match = re.search(r'\[.*?\] \d{4}-\d{2}-\d{2}.*?\| (.*?)$', block, re.MULTILINE)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        
        # Extract source
        source_match = re.search(r'Source: (.*?)$', block, re.MULTILINE)
        source = source_match.group(1).strip() if source_match else ""
        
        # Extract URL
        url_match = re.search(r'URL: (.*?)$', block, re.MULTILINE)
        url = url_match.group(1).strip() if url_match else ""
        
        # Extract summary - the rest of the text after URL
        summary = ""
        if url_match:
            rest_of_block = block[url_match.end():].strip()
            if rest_of_block:
                summary = rest_of_block
        
        if title and url:
            items.append({
                'title': title,
                'source': source,
                'url': url,
                'summary': summary
            })
    
    logger.info(f"Found {len(items)} items in {file_path}")
    return items

def main():
    parser = argparse.ArgumentParser(description="Publish backlog stories in batches.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of stories to process in this run (default: 50)",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Index of the first story to process (default: 0)",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        logger.error("Batch size must be a positive integer.")
        sys.exit(1)

    if args.start_index < 0:
        logger.error("Start index must be zero or a positive integer.")
        sys.exit(1)

    logger.info("Starting backlog publishing process")
    
    # Process Federal Register
    fr_items = process_file(project_root / "federal_register_results.txt")
    
    # Process Europol
    europol_items = process_file(project_root / "europol_results.txt")
    
    # Combine all items
    all_items = fr_items + europol_items
    
    total_items = len(all_items)
    logger.info(f"Total items to publish: {total_items}")

    if args.start_index >= total_items:
        logger.info("Start index is beyond total items. Nothing to process.")
        logger.info(f"Processed stories {args.start_index}-{args.start_index} of {total_items}")
        return

    end_index = min(args.start_index + args.batch_size, total_items)
    items_to_process = all_items[args.start_index:end_index]
    logger.info(f"Processing stories {args.start_index}-{end_index} of {total_items}")
    
    # Get list of existing stories to avoid duplicates
    docs_dir = project_root / "docs"
    published_titles = set()
    
    if docs_dir.exists():
        # Find HTML files with story titles
        html_files = list(docs_dir.glob("**/*.html"))
        logger.info(f"Found {len(html_files)} existing HTML files")
        
        # Extract titles from HTML files
        for html_file in html_files:
            try:
                with open(html_file, 'r') as f:
                    content = f.read()
                    title_match = re.search(r'<title>(.*?)</title>', content)
                    if title_match:
                        published_titles.add(title_match.group(1).strip())
            except Exception as e:
                logger.error(f"Error reading HTML file {html_file}: {e}")
    
    # Publish items
    published_count = 0
    for item in items_to_process:
        title = item.get('title', '')
        
        # Skip if already published
        if title in published_titles:
            logger.info(f"Skipping already published: {title}")
            continue
        
        summary = item.get('summary', '') or "Breaking news from government sources."
        url = item.get('url', '')
        
        if title and url:
            if publish_story(title, summary, url):
                published_count += 1
                published_titles.add(title)  # Add to published set
            
            # Short sleep to avoid overwhelming git
            time.sleep(3)
    
    logger.info(f"Published {published_count} new stories from backlog")
    logger.info(f"Processed stories {args.start_index}-{end_index} of {total_items}")

if __name__ == "__main__":
    main()
