#!/usr/bin/env python3
"""Batch processor for historical Federal Register documents."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

from scripts.monitors import NewsItem
from scripts.monitors.federal_register import FederalRegisterMonitor


logger = logging.getLogger(__name__)


class HistoricalFederalRegisterMonitor(FederalRegisterMonitor):
    """Extended monitor that can fetch documents for a specific date."""

    def fetch_for_date(self, target_date: date) -> Dict[str, Any]:
        params = {
            "conditions[publication_date]": target_date.isoformat(),
            "per_page": 100,
            "order": "newest",
        }

        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except (Exception,) as exc:  # requests raises RequestException subclasses
            logger.error("Failed to fetch Federal Register data for %s: %s", target_date, exc)
            return {"results": [], "count": 0}


_thread_local = threading.local()


def _get_thread_monitor() -> HistoricalFederalRegisterMonitor:
    """Provide one monitor instance per thread for safe session reuse."""
    monitor = getattr(_thread_local, "monitor", None)
    if monitor is None:
        monitor = HistoricalFederalRegisterMonitor()
        _thread_local.monitor = monitor
    return monitor


def _serialize_items(items: Iterable[NewsItem]) -> List[Dict[str, Any]]:
    """Convert NewsItem objects into JSON-serializable dictionaries."""
    serialized: List[Dict[str, Any]] = []
    for item in items:
        serialized.append(
            {
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "date": item.date.isoformat(),
                "content": item.content,
            }
        )
    return serialized


def process_date(target_date: date, output_dir: Path) -> int:
    """Fetch, parse, and persist Federal Register documents for a single day."""
    try:
        monitor = _get_thread_monitor()
        raw_data = monitor.fetch_for_date(target_date)
        items = list(monitor.parse(raw_data))

        output_path = output_dir / f"federal_register_{target_date.isoformat()}.json"
        payload = {
            "date": target_date.isoformat(),
            "count": len(items),
            "results": _serialize_items(items),
        }

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        return len(items)
    except Exception as exc:  # Catch-all ensures batch run continues
        logger.exception("Unexpected error while processing %s: %s", target_date, exc)
        return 0


def daterange(start: date, end: date) -> Iterable[date]:
    """Yield every date from start to end inclusive."""
    span = (end - start).days
    for offset in range(span + 1):
        yield start + timedelta(days=offset)


def main() -> None:
    """Process historical Federal Register documents over the target date range."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    output_dir = Path("logs/federal_register_history")
    output_dir.mkdir(parents=True, exist_ok=True)

    start_date = date(2025, 12, 1)
    end_date = date(2026, 1, 31)
    dates = list(daterange(start_date, end_date))

    logger.info("Starting batch Federal Register processing for %d days", len(dates))

    max_workers = min(8, max(1, len(dates)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(process_date, target_date, output_dir): target_date for target_date in dates}

        for future in as_completed(future_map):
            target_date = future_map[future]
            try:
                count = future.result()
                logger.info("Processed %s with %d documents", target_date.isoformat(), count)
            except Exception as exc:
                logger.exception("Processing failed for %s: %s", target_date, exc)

    logger.info("Completed batch Federal Register processing")


if __name__ == "__main__":
    main()
