#!/usr/bin/env python3
"""
Parallel processor for Federal Register documents with exponential backoff rate limiting.

This script processes multiple Federal Register pages in parallel
to maximize the throughput of document mining. It includes robust
rate limiting with exponential backoff to handle API limitations.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any, Optional

from scripts.monitors import NewsItem
from scripts.monitors.federal_register import FederalRegisterMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("rate_limited_register_miner")

# Thread-local storage for monitor instances
_thread_local = threading.local()

def get_thread_monitor() -> FederalRegisterMonitor:
    """Provide one monitor instance per thread for safe session reuse."""
    monitor = getattr(_thread_local, "monitor", None)
    if monitor is None:
        monitor = FederalRegisterMonitor()
        _thread_local.monitor = monitor
    return monitor

def request_with_backoff(
    monitor,
    url: str,
    params: Dict[str, Any],
    max_retries: int,
    base_delay: float,
    max_delay: float,
) -> Any:
    """
    Make an HTTP request with exponential backoff for rate limiting.
    
    Args:
        monitor: The monitor instance with a session for making requests
        url: The URL to request
        params: The query parameters for the request
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        
    Returns:
        The JSON response from the API
        
    Raises:
        Exception: If all retry attempts fail
    """
    retries = 0
    delay = base_delay
    
    while True:
        try:
            response = monitor.session.get(url, params=params, timeout=15)
            
            # Check for rate limiting
            if response.status_code == 429:
                if retries >= max_retries:
                    raise Exception(f"Exceeded maximum retries ({max_retries}) on rate limit 429")
                
                # Get retry-after header if available, otherwise use calculated delay
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                    logger.warning(f"Rate limited (429). Server specified retry after {delay}s")
                else:
                    # Add jitter (±25%) to avoid synchronized retries
                    jitter = random.uniform(0.75, 1.25)
                    delay = min(max_delay, delay * 2 * jitter)
                    logger.warning(f"Rate limited (429). Using backoff delay of {delay:.2f}s (retry {retries+1}/{max_retries})")
                
                retries += 1
                time.sleep(delay)
                continue
            
            # Raise for other HTTP errors
            response.raise_for_status()
            
            # Return parsed JSON data
            return response.json()
            
        except Exception as e:
            if "429" in str(e) and retries < max_retries:
                # Add jitter (±25%) to avoid synchronized retries
                jitter = random.uniform(0.75, 1.25)
                delay = min(max_delay, delay * 2 * jitter)
                logger.warning(f"Rate limited (429). Using backoff delay of {delay:.2f}s (retry {retries+1}/{max_retries})")
                retries += 1
                time.sleep(delay)
            elif retries < max_retries:
                # Handle connection errors or other server errors
                # Add jitter (±25%) to avoid synchronized retries
                jitter = random.uniform(0.75, 1.25)
                delay = min(max_delay, delay * 2 * jitter)
                logger.warning(f"Request error: {e}. Using backoff delay of {delay:.2f}s (retry {retries+1}/{max_retries})")
                retries += 1
                time.sleep(delay)
            else:
                logger.error(f"Failed after {max_retries} retries: {e}")
                raise

def parse_range(range_str: str) -> List[Tuple[int, int]]:
    """
    Parse a comma-separated list of ranges into a list of (start, end) tuples.
    Example: "3000-3900,4000-4500" -> [(3000, 3900), (4000, 4500)]
    """
    ranges = []
    parts = range_str.split(",")
    for part in parts:
        if "-" not in part:
            logger.warning(f"Invalid range format: {part}. Should be start-end.")
            continue
        
        try:
            start, end = map(int, part.split("-"))
            if start > end:
                logger.warning(f"Invalid range: {start}-{end}. Start should be <= end.")
                continue
            ranges.append((start, end))
        except ValueError:
            logger.warning(f"Invalid range format: {part}. Should be start-end with integers.")
    
    return ranges

def parse_date_range(range_str: str) -> Tuple[datetime, datetime]:
    """
    Parse a comma-separated date range string into start and end datetime objects.
    Ensures the range falls within 2020-01-01 and 2023-12-31 (inclusive).
    """
    parts = [part.strip() for part in range_str.split(",")]
    if len(parts) != 2:
        raise ValueError("Date range must contain exactly two dates separated by a comma.")
    
    try:
        start_date = datetime.strptime(parts[0], "%Y-%m-%d")
        end_date = datetime.strptime(parts[1], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Dates must be in YYYY-MM-DD format.") from exc
    
    earliest = datetime(2020, 1, 1)
    latest = datetime(2023, 12, 31, 23, 59, 59)
    
    if start_date < earliest or end_date > latest:
        raise ValueError("Date range must be within 2020-01-01 and 2023-12-31.")
    
    if start_date > end_date:
        raise ValueError("Start date must be on or before end date.")
    
    return start_date, end_date

def process_page_range(
    start_page: int,
    end_page: int,
    per_page: int,
    temp_dir: Path,
    date_range: Optional[Tuple[datetime, datetime]] = None,
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
) -> str:
    """
    Process a specific page range from the Federal Register API with rate limiting
    and save results to a temporary file.
    
    Args:
        start_page: The first page to process
        end_page: The last page to process
        per_page: Number of items per page
        temp_dir: Directory to store temporary output files
        date_range: Optional tuple of (start_date, end_date) to filter by publication date
        max_retries: Maximum number of retry attempts for rate limiting
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        
    Returns:
        Path to the temporary file containing the results
    """
    monitor = get_thread_monitor()
    logger.info(f"Processing page range {start_page}-{end_page} with {per_page} items per page")
    
    # Create a temporary file for this thread
    thread_id = threading.get_ident()
    temp_file = temp_dir / f"register_range_{start_page}_{end_page}_{thread_id}.txt"
    
    all_items = []
    processed_pages = 0
    total_pages = end_page - start_page + 1
    
    # Process each page in the range
    for current_page in range(start_page, end_page + 1):
        try:
            # Set up parameters for the Federal Register API
            params = {
                "per_page": per_page,
                "page": current_page,
                "order": "relevance",
            }

            if date_range:
                start_date, end_date = date_range
                params["conditions[publication_date][gte]"] = start_date.strftime("%Y-%m-%d")
                params["conditions[publication_date][lte]"] = end_date.strftime("%Y-%m-%d")
            
            # Fetch the page with backoff for rate limiting
            data = request_with_backoff(
                monitor=monitor,
                url=monitor.BASE_URL,
                params=params,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
            )
            
            # Process the results
            if "results" in data and isinstance(data["results"], list):
                items = list(monitor.parse(data))
                all_items.extend(items)
                logger.info(f"Found {len(items)} items on page {current_page}")
            else:
                logger.warning(f"No results found on page {current_page}")
            
        except Exception as e:
            logger.error(f"Error processing page {current_page}: {e}")
        
        processed_pages += 1
        logger.info(f"Processed {processed_pages}/{total_pages} pages from range {start_page}-{end_page}")
    
    # Write results to the temporary file
    with temp_file.open("w", encoding="utf-8") as f:
        for item in all_items:
            tag = f"[FEDERAL REGISTER PAGE {start_page}-{end_page}]"
            date_str = item.date.strftime("%Y-%m-%d %H:%M:%SZ")
            
            f.write(f"{tag} {date_str} | {item.title}\n")
            f.write(f"Source: {item.source}\n")
            f.write(f"URL: {item.url}\n")
            f.write(f"{item.content}\n")
            f.write("-" * 80 + "\n")
    
    logger.info(f"Saved {len(all_items)} items from page range {start_page}-{end_page} to {temp_file}")
    return str(temp_file)

def get_existing_titles() -> Set[str]:
    """Get a set of already published story titles from the docs directory."""
    docs_dir = Path(__file__).parent / "docs"
    published_titles = set()
    
    if docs_dir.exists():
        # Find HTML files with story titles
        html_files = list(docs_dir.glob("**/*.html"))
        logger.info(f"Found {len(html_files)} existing HTML files")
        
        # Extract titles from HTML files
        for html_file in html_files:
            try:
                with open(html_file, "r") as f:
                    content = f.read()
                    title_match = re.search(r"<title>(.*?)</title>", content)
                    if title_match:
                        published_titles.add(title_match.group(1).strip())
            except Exception as e:
                logger.error(f"Error reading HTML file {html_file}: {e}")
    
    return published_titles

def merge_temp_files(temp_files: List[str], output_file: Path, existing_titles: Set[str]) -> int:
    """
    Merge multiple temporary files into the final output file.
    Returns the number of new items added.
    """
    logger.info(f"Merging {len(temp_files)} temporary files into {output_file}")
    
    # Parse existing output file if it exists
    existing_urls = set()
    existing_content = ""
    if output_file.exists():
        try:
            with output_file.open("r", encoding="utf-8") as f:
                existing_content = f.read()
                
                # Extract URLs from existing content to avoid duplicates
                for url_match in re.finditer(r"URL: (.*?)$", existing_content, re.MULTILINE):
                    existing_urls.add(url_match.group(1).strip())
        except Exception as e:
            logger.error(f"Error reading existing output file: {e}")
    
    # Process all temporary files
    new_items = []
    for temp_file in temp_files:
        try:
            with open(temp_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Split into individual news items using the divider line
            news_blocks = content.split("-" * 80)
            
            for block in news_blocks:
                if not block.strip():
                    continue
                
                # Extract URL to check for duplicates
                url_match = re.search(r"URL: (.*?)$", block, re.MULTILINE)
                url = url_match.group(1).strip() if url_match else ""
                
                # Extract title to check for duplicates
                title_match = re.search(r"\[.*?\] \d{4}-\d{2}-\d{2}.*?\| (.*?)$", block, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else ""
                
                # Skip duplicates by URL or title
                if url and url not in existing_urls and title and title not in existing_titles:
                    new_items.append(block)
                    existing_urls.add(url)
                    existing_titles.add(title)
        except Exception as e:
            logger.error(f"Error processing temporary file {temp_file}: {e}")
    
    # Write merged content to output file
    if new_items:
        header = [
            "=" * 80,
            f"Federal Register Parallel Mining Results ({len(new_items)} new items)",
            "=" * 80,
            "",
        ]
        
        separator = "-" * 80
        body = [item + separator for item in new_items]
        
        # Combine with existing content or create new
        if existing_content:
            # Find the position after the header to insert new items
            header_end = existing_content.find("=" * 80 + "\n\n")
            if header_end > 0:
                insert_pos = header_end + len("=" * 80 + "\n\n")
                combined = existing_content[:insert_pos] + "\n".join(body) + "\n" + existing_content[insert_pos:]
            else:
                combined = "\n".join(header + body + [""])
        else:
            combined = "\n".join(header + body + [""])
        
        with output_file.open("w", encoding="utf-8") as f:
            f.write(combined)
    
    return len(new_items)

def main():
    parser = argparse.ArgumentParser(description="Process Federal Register documents in parallel with rate limiting.")
    parser.add_argument(
        "--num-threads",
        type=int,
        default=4,
        help="Number of threads to use (default: 4)",
    )
    parser.add_argument(
        "--page-ranges",
        type=str,
        default="30-40,40-50,50-60,60-70",
        help="Comma-separated list of page ranges to process (e.g., 30-40,40-50)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Number of items per page (default: 100)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("federal_register_results.txt"),
        help="Output file for results (default: federal_register_results.txt)",
    )
    parser.add_argument(
        "--date-range",
        type=str,
        default=None,
        help="Historical date range to query in format YYYY-MM-DD,YYYY-MM-DD (2020-2023).",
    )
    # Add rate limiting parameters
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum number of retry attempts for rate limiting (default: 5)",
    )
    parser.add_argument(
        "--base-delay",
        type=float,
        default=2.0,
        help="Initial delay between retries in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=60.0,
        help="Maximum delay between retries in seconds (default: 60.0)",
    )
    args = parser.parse_args()
    
    # Parse page ranges
    ranges = parse_range(args.page_ranges)
    if not ranges:
        logger.error("No valid page ranges specified.")
        sys.exit(1)

    date_range: Optional[Tuple[datetime, datetime]] = None
    if args.date_range:
        try:
            date_range = parse_date_range(args.date_range)
        except ValueError as exc:
            logger.error(f"Invalid date range: {exc}")
            sys.exit(1)
        else:
            logger.info(
                "Restricting queries to publication dates between %s and %s",
                date_range[0].strftime("%Y-%m-%d"),
                date_range[1].strftime("%Y-%m-%d"),
            )
    
    # Create temporary directory for thread outputs
    temp_dir = Path("logs/temp_parallel_mining")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Get existing published titles
    existing_titles = get_existing_titles()
    logger.info(f"Found {len(existing_titles)} existing published titles")
    
    # Process page ranges in parallel
    logger.info(
        f"Starting parallel processing with {args.num_threads} threads "
        f"for page ranges: {args.page_ranges} "
        f"(max_retries={args.max_retries}, base_delay={args.base_delay}s, max_delay={args.max_delay}s)"
    )
    temp_files = []
    
    with ThreadPoolExecutor(max_workers=args.num_threads) as executor:
        futures = []
        
        for start, end in ranges:
            future = executor.submit(
                process_page_range,
                start_page=start,
                end_page=end,
                per_page=args.per_page,
                temp_dir=temp_dir,
                date_range=date_range,
                max_retries=args.max_retries,
                base_delay=args.base_delay,
                max_delay=args.max_delay,
            )
            futures.append(future)
        
        for future in as_completed(futures):
            try:
                temp_file = future.result()
                temp_files.append(temp_file)
            except Exception as e:
                logger.error(f"Error in thread: {e}")
    
    # Merge results
    new_items_count = merge_temp_files(temp_files, args.output_file, existing_titles)
    logger.info(f"Added {new_items_count} new items to {args.output_file}")
    
    # Clean up temporary files
    for temp_file in temp_files:
        try:
            os.remove(temp_file)
        except OSError:
            pass
    
    logger.info(f"Parallel processing complete. Results saved to {args.output_file}")

if __name__ == "__main__":
    main()
