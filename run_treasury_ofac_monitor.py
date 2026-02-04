#!/usr/bin/env python3

"""
Script to run the Treasury & OFAC monitor and publish new findings.
"""

import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root and scripts directory are on the path
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "scripts"))

from scripts.monitors.treasury_ofac_monitor import TreasuryOFACMonitor  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("treasury_ofac_monitor")


def get_published_at(item) -> datetime:
    """Safely extract the publication datetime for sorting and logging."""
    published = getattr(item, "published_at", None)
    if isinstance(published, datetime):
        return published
    return datetime.now(timezone.utc)


def is_breaking_item(monitor: TreasuryOFACMonitor, item) -> bool:
    """Determine whether the news item qualifies as breaking (published today UTC)."""
    if hasattr(monitor, "check_if_breaking"):
        try:
            return bool(monitor.check_if_breaking(item))
        except Exception:
            logger.exception("Error checking if item is breaking via monitor hook")

    published = get_published_at(item)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def publish_news_item(item) -> bool:
    """Publish a news item using the publish_story.sh helper script."""
    title = getattr(item, "title", "Untitled Treasury/OFAC Update")
    summary = getattr(
        item,
        "summary",
        "Breaking sanctions update from the U.S. Treasury and OFAC.",
    )
    link = getattr(item, "link", "")

    logger.info("Publishing: %s", title)

    try:
        subprocess.run(
            [
                str(project_root / "publish_story.sh"),
                title,
                summary or "Breaking sanctions update from the U.S. Treasury and OFAC.",
                link,
            ],
            check=True,
        )
        logger.info("Successfully published: %s", title)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Error publishing %s: %s", title, exc)
        return False


def main():
    logger.info("Starting Treasury & OFAC monitor")

    monitor = TreasuryOFACMonitor()

    try:
        logger.info("Fetching data from Treasury and OFAC...")
        raw_data = monitor.fetch()

        logger.info("Parsing Treasury and OFAC data...")
        news_items = list(monitor.parse(raw_data))

        if not news_items:
            logger.info("No news items found from Treasury or OFAC")
            return

        logger.info("Found %d news items", len(news_items))

        breaking_items = [item for item in news_items if is_breaking_item(monitor, item)]

        if breaking_items:
            logger.info("Found %d breaking news items from today", len(breaking_items))
            for item in breaking_items:
                logger.info(
                    "Processing item: %s - %s - %s",
                    getattr(item, "title", "Untitled"),
                    getattr(item, "source", "unknown-source"),
                    get_published_at(item),
                )
                publish_news_item(item)
        else:
            logger.info("No breaking news items found from today")
            recent_items = sorted(
                news_items,
                key=get_published_at,
                reverse=True,
            )[:3]

            if recent_items:
                logger.info(
                    "Publishing %d most recent Treasury/OFAC items", len(recent_items)
                )
                for item in recent_items:
                    logger.info(
                        "Processing recent item: %s - %s - %s",
                        getattr(item, "title", "Untitled"),
                        getattr(item, "source", "unknown-source"),
                        get_published_at(item),
                    )
                    publish_news_item(item)

    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception("Error running Treasury & OFAC monitor: %s", exc)


if __name__ == "__main__":
    main()
