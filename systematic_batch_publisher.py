#!/usr/bin/env python3

"""
Systematic Batch Publisher for Historical Federal Register Documents

This script implements a robust batch publishing system for the backlog of
historical Federal Register documents (2020-2023) with rate limiting,
systematic rotation through years, and detailed progress tracking.
"""

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("systematic_publisher")

# Project root
PROJECT_ROOT = Path(__file__).parent.resolve()
LOG_DIR = PROJECT_ROOT / "logs" / "publishing_runs"
HISTORICAL_DIR = PROJECT_ROOT / "logs" / "historical_runs"
PUBLISH_SCRIPT = PROJECT_ROOT / "publish_historical_stories.py"


def setup_directories():
    """Ensure all required directories exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)


def load_progress():
    """Load the publishing progress from a JSON file."""
    progress_file = LOG_DIR / "publishing_progress.json"
    
    if not progress_file.exists():
        logger.info("No existing progress file found. Creating new progress tracking.")
        return {
            "2020": {"published": 0, "total": 2648, "last_batch": 0},
            "2021": {"published": 0, "total": 2651, "last_batch": 0},
            "2022": {"published": 0, "total": 2654, "last_batch": 0},
            "2023": {"published": 0, "total": 2635, "last_batch": 0},
            "total_published": 0,
            "total_remaining": 10588,
            "last_update": datetime.now().isoformat()
        }
    
    try:
        with progress_file.open("r") as f:
            progress = json.load(f)
            logger.info(f"Loaded existing progress: {progress['total_published']} published, {progress['total_remaining']} remaining")
            return progress
    except Exception as e:
        logger.error(f"Error loading progress file: {e}")
        sys.exit(1)


def save_progress(progress):
    """Save the publishing progress to a JSON file."""
    progress_file = LOG_DIR / "publishing_progress.json"
    progress["last_update"] = datetime.now().isoformat()
    
    try:
        with progress_file.open("w") as f:
            json.dump(progress, f, indent=2)
        logger.info(f"Progress saved: {progress['total_published']} published, {progress['total_remaining']} remaining")
    except Exception as e:
        logger.error(f"Error saving progress file: {e}")


def update_progress(progress, year, batch_size):
    """Update the progress tracking after a successful batch."""
    progress[year]["published"] += batch_size
    progress[year]["last_batch"] = batch_size
    progress["total_published"] += batch_size
    progress["total_remaining"] -= batch_size
    
    # Ensure we don't go negative on remaining counts
    if progress["total_remaining"] < 0:
        progress["total_remaining"] = 0
    
    save_progress(progress)
    return progress


def process_year(year, batch_size, max_retries=3, base_delay=5):
    """Process a batch of stories from a specific year with exponential backoff."""
    logger.info(f"Processing year {year} with batch size {batch_size}")
    
    retry_count = 0
    delay = base_delay
    
    while retry_count < max_retries:
        try:
            # Run the publishing script for this year
            cmd = [
                "python3",
                str(PUBLISH_SCRIPT),
                "--year", str(year),
                "--batch-size", str(batch_size)
            ]
            
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Check for successful publication in output
            output = result.stdout
            logger.info(f"Command output: {output}")
            
            # Publication successful
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error processing year {year}: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            
            # Implement exponential backoff
            retry_count += 1
            if retry_count < max_retries:
                jitter = random.uniform(0.75, 1.25)
                delay = min(300, delay * 2 * jitter)  # Cap at 5 minutes
                logger.info(f"Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})")
                time.sleep(delay)
            else:
                logger.error(f"Failed after {max_retries} retries for year {year}")
                return False
        
        except Exception as e:
            logger.error(f"Unexpected error processing year {year}: {e}")
            retry_count += 1
            if retry_count < max_retries:
                jitter = random.uniform(0.75, 1.25)
                delay = min(300, delay * 2 * jitter)
                logger.info(f"Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})")
                time.sleep(delay)
            else:
                logger.error(f"Failed after {max_retries} retries for year {year}")
                return False
    
    return False


def push_to_repository():
    """Commit and push changes to the repository."""
    logger.info("Pushing changes to repository")
    
    try:
        # Add all files
        subprocess.run(
            ["git", "add", "-A"],
            cwd=PROJECT_ROOT,
            check=True
        )
        
        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=PROJECT_ROOT,
            capture_output=True
        )
        
        # Exit code 1 means there are differences (changes to commit)
        if result.returncode == 1:
            # Commit
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subprocess.run(
                ["git", "commit", "-m", f"Published historical Federal Register stories {timestamp}"],
                cwd=PROJECT_ROOT,
                check=True
            )
            
            # Push
            subprocess.run(
                ["git", "push"],
                cwd=PROJECT_ROOT,
                check=True
            )
            
            logger.info("Successfully committed and pushed changes")
            return True
        else:
            logger.info("No changes to commit")
            return True
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Systematically publish historical Federal Register documents"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of stories to process in each batch (default: 50)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous mode, processing all years in rotation"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=10,
        help="Maximum number of batches to process in continuous mode (default: 10)"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Delay in minutes between batches in continuous mode (default: 5)"
    )
    parser.add_argument(
        "--year",
        type=str,
        choices=["2020", "2021", "2022", "2023"],
        help="Process a specific year only (default: rotate through all years)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually publishing"
    )
    
    args = parser.parse_args()
    
    if args.batch_size <= 0:
        logger.error("Batch size must be positive")
        sys.exit(1)
    
    if args.continuous and args.max_batches <= 0:
        logger.error("Max batches must be positive in continuous mode")
        sys.exit(1)
    
    setup_directories()
    progress = load_progress()
    
    # Log starting point
    total_published = progress["total_published"]
    total_remaining = progress["total_remaining"]
    logger.info(f"Starting systematic publishing with {total_published} stories already published")
    logger.info(f"Remaining stories to publish: {total_remaining}")
    
    # Print per-year status
    for year in ["2020", "2021", "2022", "2023"]:
        year_data = progress[year]
        logger.info(f"Year {year}: {year_data['published']} published of {year_data['total']} total")
    
    if args.dry_run:
        logger.info("DRY RUN MODE: No actual publishing will occur")
    
    # Single year mode
    if args.year:
        year = args.year
        logger.info(f"Processing single year: {year}")
        
        if not args.dry_run:
            success = process_year(year, args.batch_size)
            if success:
                update_progress(progress, year, args.batch_size)
                push_to_repository()
            else:
                logger.error(f"Failed to process year {year}")
        else:
            logger.info(f"DRY RUN: Would process {args.batch_size} stories from year {year}")
        
        logger.info("Single year processing complete")
        return
    
    # Continuous rotation mode
    if args.continuous:
        logger.info(f"Starting continuous mode with {args.max_batches} batches")
        batch_count = 0
        
        while batch_count < args.max_batches:
            # Rotate through years: 2023, 2022, 2021, 2020, repeat
            year = str(2023 - (batch_count % 4))
            logger.info(f"Batch {batch_count+1}/{args.max_batches}: Processing year {year}")
            
            if not args.dry_run:
                success = process_year(year, args.batch_size)
                if success:
                    update_progress(progress, year, args.batch_size)
                    push_to_repository()
                else:
                    logger.error(f"Failed to process year {year}")
                    # Add delay before retrying
                    delay_seconds = 60  # 1 minute retry delay on failure
                    logger.info(f"Waiting {delay_seconds} seconds before continuing...")
                    time.sleep(delay_seconds)
            else:
                logger.info(f"DRY RUN: Would process {args.batch_size} stories from year {year}")
            
            batch_count += 1
            
            # Don't sleep after the last batch
            if batch_count < args.max_batches and not args.dry_run:
                delay_seconds = args.delay * 60
                logger.info(f"Waiting {args.delay} minutes before next batch...")
                time.sleep(delay_seconds)
        
        logger.info(f"Completed {batch_count} batches in continuous mode")
        return
    
    # Default: process all years once
    logger.info("Processing all years once in sequence")
    
    for year in ["2023", "2022", "2021", "2020"]:
        logger.info(f"Processing year {year}")
        
        if not args.dry_run:
            success = process_year(year, args.batch_size)
            if success:
                update_progress(progress, year, args.batch_size)
            else:
                logger.error(f"Failed to process year {year}")
        else:
            logger.info(f"DRY RUN: Would process {args.batch_size} stories from year {year}")
    
    if not args.dry_run:
        push_to_repository()
    
    logger.info("All years processed")


if __name__ == "__main__":
    main()
