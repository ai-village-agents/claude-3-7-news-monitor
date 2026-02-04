#!/usr/bin/env python3
"""
Aggregate historical Federal Register JSON payloads into the standard backlog format.

This utility converts the per-day JSON exports created by batch_federal_register.py
into the plain-text structure expected by publish_backlog.py. The script performs
basic validation, deduplication, and ordering so the publishing pipeline can treat
the historical backlog the same way it handles freshly scraped content.
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DEFAULT_INPUT_DIR = Path("logs/federal_register_history")
DEFAULT_OUTPUT_FILE = Path("federal_register_results.txt")
DEFAULT_WORKERS = 8

logger = logging.getLogger("process_historical_register")


def configure_logging(verbose: bool) -> None:
    """Configure root logging once for both console visibility and automation."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for configurable input, output, and runtime behavior."""
    parser = argparse.ArgumentParser(
        description="Convert historical Federal Register JSON exports into backlog format."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing per-day JSON exports (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Destination file for combined backlog output (default: %(default)s).",
    )
    parser.add_argument(
        "--tag",
        default="[FEDERAL REGISTER ARCHIVE]",
        help="Prefix tag for each backlog entry (default: %(default)s).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Maximum thread workers used to load JSON files (default: %(default)s).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip rewriting the output if it already exists and would be identical.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )
    return parser.parse_args()


def load_json_file(path: Path) -> Iterable[Dict[str, object]]:
    """
    Load a single JSON history file and yield the structured news entries.

    Any parsing errors are logged and will not abort the entire run; the caller
    simply receives no entries for the problematic file.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return []

    results = payload.get("results")
    if not isinstance(results, list):
        logger.warning("File %s has unexpected structure; skipping", path)
        return []

    return results


def normalize_iso_timestamp(raw_value: str) -> Tuple[str, datetime]:
    """
    Convert an ISO-8601 string into a display timestamp and datetime object.

    Historical exports typically contain UTC timestamps with offsets; we normalise
    them to the canonical Federal Register format YYYY-MM-DD HH:MM:SSZ while
    retaining the parsed datetime for sorting and deduplication purposes.
    """
    if raw_value.endswith("Z"):
        raw_value = raw_value[:-1] + "+00:00"

    dt = datetime.fromisoformat(raw_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    display = dt.strftime("%Y-%m-%d %H:%M:%SZ")
    return display, dt


def sanitise_summary(text: Optional[str]) -> str:
    """Collapse whitespace in the summary so the backlog remains single-line."""
    if not text:
        return "Federal Register notice with no supplied summary."
    collapsed = " ".join(text.split())
    return collapsed if collapsed else "Federal Register notice with no supplied summary."


def collect_items(file_paths: List[Path], max_workers: int) -> List[Dict[str, object]]:
    """
    Concurrently load JSON entries from disk and return a de-duplicated list.

    Deduplication is performed using document URLs which are stable across fetches.
    The most recent entry wins if duplicates are encountered.
    """
    logger.info("Loading %d history file(s) using up to %d worker(s)", len(file_paths), max_workers)
    items_by_url: Dict[str, Dict[str, object]] = {}

    # ThreadPoolExecutor keeps I/O saturated when many history files are present.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for entries in executor.map(load_json_file, file_paths):
            for entry in entries:
                url = entry.get("url")
                if not url:
                    continue
                summary = sanitise_summary(entry.get("content"))
                try:
                    timestamp_raw = str(entry.get("date"))
                    display_ts, dt_obj = normalize_iso_timestamp(timestamp_raw)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Skipping entry due to timestamp parsing error: %s", exc)
                    continue

                items_by_url[url] = {
                    "title": str(entry.get("title", "")).strip() or "Untitled Federal Register notice",
                    "source": str(entry.get("source", "Federal Register")) or "Federal Register",
                    "url": url,
                    "summary": summary,
                    "display_timestamp": display_ts,
                    "datetime": dt_obj,
                }

    items = list(items_by_url.values())
    logger.info("Collected %d unique notice(s)", len(items))
    return items


def format_backlog(items: List[Dict[str, object]], tag: str) -> str:
    """Render the combined backlog file as a single string."""
    if not items:
        header = [
            "=" * 80,
            "Federal Register Historical Backlog (0 items)",
            "=" * 80,
            "",
            "No historical items were available.",
            "",
        ]
        return "\n".join(header)

    # Order items newest-first for easier review and publication.
    items.sort(key=lambda payload: payload["datetime"], reverse=True)

    header = [
        "=" * 80,
        f"Federal Register Historical Backlog ({len(items)} items)",
        "=" * 80,
        "",
    ]

    body_lines: List[str] = []
    separator = "-" * 80

    for item in items:
        body_lines.extend(
            [
                f"{tag} {item['display_timestamp']} | {item['title']}",
                f"Source: {item['source']}",
                f"URL: {item['url']}",
                item["summary"],
                separator,
            ]
        )

    # Drop trailing separator for neatness.
    if body_lines and body_lines[-1] == separator:
        body_lines.pop()

    return "\n".join(header + body_lines) + "\n"


def write_output(path: Path, content: str, skip_existing: bool) -> None:
    """Persist the formatted backlog, optionally short-circuiting if unchanged."""
    if skip_existing and path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read existing output %s: %s", path, exc)
        else:
            if existing == content:
                logger.info("Output %s already up to date; skipping write.", path)
                return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write combined backlog to %s: %s", path, exc)
        raise
    else:
        logger.info("Wrote combined backlog to %s", path)


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)

    input_dir = args.input_dir
    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("Input directory not found or not a directory: %s", input_dir)
        return

    file_paths = sorted(input_dir.glob("*.json"))
    if not file_paths:
        logger.warning("No JSON files found in %s; nothing to process.", input_dir)
        return

    max_workers = max(1, args.max_workers)
    items = collect_items(file_paths, max_workers=max_workers)
    backlog = format_backlog(items, tag=args.tag)
    write_output(args.output, backlog, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
