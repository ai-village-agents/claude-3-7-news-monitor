#!/usr/bin/env python3
"""
Publish stories mined from historical Federal Register runs.

This script scans the results in logs/historical_runs, extracts individual
stories, and publishes them with publish_story_improved.sh. It supports
limiting the number of publications per run and optionally restricting
processing to a single year.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("historical_publisher")

PROJECT_ROOT = Path(__file__).parent.resolve()
RESULTS_DIR = PROJECT_ROOT / "logs" / "historical_runs"
PUBLISH_SCRIPT = PROJECT_ROOT / "publish_story_improved.sh"


@dataclass
class Story:
    """Container for a parsed story."""

    title: str
    summary: str
    url: str
    source: str
    origin_file: Path


def gather_results_files(year: Optional[int]) -> List[Path]:
    """
    Return the list of historical results files to process.
    """
    if not RESULTS_DIR.exists():
        logger.error("Results directory not found: %s", RESULTS_DIR)
        return []

    if year is not None:
        candidate = RESULTS_DIR / f"federal_register_results_{year}.txt"
        if candidate.exists():
            return [candidate]
        logger.error("No results file found for year %s at %s", year, candidate)
        return []

    files = sorted(RESULTS_DIR.glob("*.txt"))
    if not files:
        logger.warning("No historical result files found in %s", RESULTS_DIR)
    return files


def parse_story_blocks(file_path: Path) -> Iterable[str]:
    """
    Yield raw story blocks separated by the 80-character divider.
    """
    divider = "-" * 80
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Unable to read %s: %s", file_path, exc)
        return []

    for block in content.split(divider):
        if block.strip():
            yield block


def extract_story(block: str, origin_file: Path) -> Optional[Story]:
    """
    Parse a story block into a Story instance.
    """
    title_match = re.search(r"\[.*?\]\s+\d{4}-\d{2}-\d{2}.*?\|\s+(.*?)$", block, re.MULTILINE)
    url_match = re.search(r"URL:\s+(.*?)$", block, re.MULTILINE)

    if not title_match or not url_match:
        return None

    title = title_match.group(1).strip()
    url = url_match.group(1).strip()

    if not title or not url:
        return None

    source_match = re.search(r"Source:\s+(.*?)$", block, re.MULTILINE)
    source = source_match.group(1).strip() if source_match else ""

    summary_start = url_match.end()
    summary = block[summary_start:].strip()
    if not summary:
        summary = "Highlights from the Federal Register historical mining run."

    return Story(
        title=title,
        summary=summary,
        url=url,
        source=source,
        origin_file=origin_file,
    )


def parse_results_file(file_path: Path) -> List[Story]:
    """
    Extract all stories from a given results file.
    """
    stories: List[Story] = []
    for block in parse_story_blocks(file_path):
        story = extract_story(block, file_path)
        if story:
            stories.append(story)
        else:
            logger.debug("Skipped unparseable block in %s", file_path)
    logger.info("Found %d stories in %s", len(stories), file_path)
    return stories


def load_published_titles() -> Set[str]:
    """
    Collect titles from existing HTML files in docs/ to avoid duplicates.
    """
    docs_dir = PROJECT_ROOT / "docs"
    titles: Set[str] = set()

    if not docs_dir.exists():
        return titles

    for html_file in docs_dir.glob("**/*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.MULTILINE)
        if match:
            titles.add(match.group(1).strip())
    logger.info("Loaded %d existing published titles", len(titles))
    return titles


def publish_story(story: Story) -> bool:
    """
    Publish a single story via publish_story_improved.sh.
    """
    logger.info("Publishing '%s' from %s", story.title, story.origin_file.name)
    try:
        subprocess.run(
            [
                str(PUBLISH_SCRIPT),
                story.title,
                story.summary,
                story.url,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to publish '%s': %s", story.title, exc)
        return False
    return True


def collect_stories(files: Iterable[Path]) -> List[Story]:
    """
    Flatten stories from the provided files.
    """
    collected: List[Story] = []
    for file_path in files:
        collected.extend(parse_results_file(file_path))
    return collected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish stories from historical Federal Register results.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of stories to publish in this run (default: 100).",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Only process stories from the specified year (e.g., 2021).",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        logger.error("Batch size must be a positive integer.")
        return 1

    if not PUBLISH_SCRIPT.exists():
        logger.error("Publish script not found: %s", PUBLISH_SCRIPT)
        return 1

    files = gather_results_files(args.year)
    if not files:
        logger.warning("No files to process. Exiting.")
        return 0

    all_stories = collect_stories(files)
    if not all_stories:
        logger.info("No stories found to publish.")
        return 0

    published_titles = load_published_titles()

    stories_to_publish: List[Story] = []
    duplicate_count = 0
    for story in all_stories:
        if len(stories_to_publish) >= args.batch_size:
            break
        if story.title in published_titles:
            duplicate_count += 1
            continue
        stories_to_publish.append(story)

    if not stories_to_publish:
        logger.info("No unpublished stories available within the specified criteria.")
        logger.info("Skipped as duplicates: %d", duplicate_count)
        return 0

    success_count = 0
    failure_count = 0

    for story in stories_to_publish:
        if publish_story(story):
            success_count += 1
            published_titles.add(story.title)
        else:
            failure_count += 1

    logger.info("Publishing complete.")
    logger.info("Stories attempted: %d", len(stories_to_publish))
    logger.info("Successes: %d", success_count)
    logger.info("Failures: %d", failure_count)
    logger.info("Skipped duplicates before publishing: %d", duplicate_count)

    if failure_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
