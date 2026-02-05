#!/usr/bin/env python3
"""
Parallel Federal Register index range miner.

This script processes numeric index ranges against the Federal Register
documents API. It retrieves batches in parallel, deduplicates them against
an existing backlog file, and rewrites the combined backlog once all
workers complete.
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from scripts.monitors import NewsItem
from scripts.monitors.federal_register import FederalRegisterMonitor


logger = logging.getLogger("parallel_register_miner")

DEFAULT_THREADS = 4
DEFAULT_INDEX_RANGES = "3000-3900"
DEFAULT_BATCH_SIZE = 100
DEFAULT_OUTPUT_FILE = Path("federal_register_results.txt")
DEFAULT_TAG = "[FEDERAL REGISTER INDEX]"

SEPARATOR_LINE = "-" * 80
PAGE_SIZE_CAP = 1000

_THREAD_LOCAL = threading.local()


def configure_logging() -> None:
    """Initialise root logging for CLI visibility."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for parallel index mining."""
    parser = argparse.ArgumentParser(
        description="Parallel Federal Register index range miner."
    )
    parser.add_argument(
        "--num-threads",
        type=int,
        default=DEFAULT_THREADS,
        help="Number of worker threads (default: %(default)s).",
    )
    parser.add_argument(
        "--index-ranges",
        default=DEFAULT_INDEX_RANGES,
        help="Comma separated index ranges (e.g. 3000-3900,4000-4500).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Approximate number of records fetched per API request (default: %(default)s).",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Backlog file to update (default: %(default)s).",
    )
    return parser.parse_args()


def parse_index_ranges(ranges: str) -> List[Tuple[int, int]]:
    """Convert the CLI index ranges string into a list of inclusive tuples."""
    parsed: List[Tuple[int, int]] = []
    for part in ranges.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            try:
                start_val = int(start_raw.strip())
                end_val = int(end_raw.strip())
            except ValueError as exc:  # noqa: BLE001
                raise ValueError(f"Invalid index range '{token}'") from exc
        else:
            try:
                start_val = end_val = int(token)
            except ValueError as exc:  # noqa: BLE001
                raise ValueError(f"Invalid index '{token}'") from exc
        if start_val > end_val:
            raise ValueError(f"Range start {start_val} greater than end {end_val} in '{token}'")
        parsed.append((start_val, end_val))
    if not parsed:
        raise ValueError("At least one index range must be provided.")
    return parsed


def sanitize_summary(text: Optional[str]) -> str:
    """Collapse whitespace for backlog summaries."""
    if not text:
        return "Federal Register notice with no supplied summary."
    collapsed = " ".join(str(text).split())
    return collapsed if collapsed else "Federal Register notice with no supplied summary."


def _parse_tag_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Extract tag, timestamp, and title from the backlog headline line."""
    # Example: [FEDERAL REGISTER ARCHIVE] 2026-02-04 00:00:00Z | Title
    if "|" not in line:
        return None
    lhs, title = line.split("|", 1)
    title = title.strip()
    parts = lhs.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    tag = parts[0].strip()
    timestamp = parts[1].strip()
    return tag, timestamp, title


def load_existing_entries(path: Path) -> Tuple[List[Dict[str, Any]], Set[str], str]:
    """Parse an existing backlog file into structured entries and URL set."""
    entries: List[Dict[str, Any]] = []
    urls: Set[str] = set()
    tag_default = DEFAULT_TAG

    if not path.exists():
        logger.info("Output file %s not found; starting with empty backlog.", path)
        return entries, urls, tag_default

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read existing backlog %s: %s", path, exc)
        return entries, urls, tag_default

    for block in raw_text.split(SEPARATOR_LINE):
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue

        tag_line = _parse_tag_line(lines[0])
        if not tag_line:
            continue

        tag, timestamp, title = tag_line
        tag_default = tag  # Preserve whichever tag is present.

        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            logger.debug("Skipping entry with malformed timestamp: %s", timestamp)
            continue

        source = "Federal Register"
        batch_marker: Optional[str] = None
        url: Optional[str] = None
        summary_lines: List[str] = []

        for idx, line in enumerate(lines[1:], 1):
            if line.startswith("Source: "):
                source = line.split(":", 1)[1].strip() or "Federal Register"
            elif line.startswith("Batch File: "):
                batch_marker = line.split(":", 1)[1].strip() or None
            elif line.startswith("URL: "):
                url = line.split(":", 1)[1].strip() or None
                summary_lines = lines[idx + 1 :]
                break

        if not url:
            logger.debug("Skipping entry with no URL: %s", title)
            continue

        summary = "\n".join(summary_lines).strip()
        entry = {
            "title": title,
            "source": source,
            "url": url,
            "summary": summary,
            "datetime": dt,
            "display_timestamp": timestamp,
            "batch_marker": batch_marker,
            "tag": tag,
        }
        entries.append(entry)
        urls.add(url)

    logger.info("Loaded %d existing backlog entr%s", len(entries), "y" if len(entries) == 1 else "ies")
    return entries, urls, tag_default


def format_backlog(items: Iterable[Dict[str, Any]], tag: str) -> str:
    """Render backlog entries into the on-disk plain text structure."""
    payload = list(items)
    if not payload:
        header = [
            "=" * 80,
            "Federal Register Historical Backlog (0 items)",
            "=" * 80,
            "",
            "No Federal Register index range results were available.",
            "",
        ]
        return "\n".join(header)

    payload.sort(key=lambda entry: entry["datetime"], reverse=True)

    header = [
        "=" * 80,
        f"Federal Register Historical Backlog ({len(payload)} items)",
        "=" * 80,
        "",
    ]

    body_lines: List[str] = []
    for entry in payload:
        display_ts = entry.get("display_timestamp")
        if not display_ts:
            display_ts = entry["datetime"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        entry_lines = [
            f"{entry.get('tag', tag)} {display_ts} | {entry['title']}",
            f"Source: {entry.get('source', 'Federal Register')}",
        ]
        batch_marker = entry.get("batch_marker")
        if batch_marker:
            entry_lines.append(f"Batch File: {batch_marker}")
        entry_lines.append(f"URL: {entry['url']}")
        summary = entry.get("summary", "").strip()
        if summary:
            entry_lines.append(summary)
        body_lines.extend(entry_lines + [SEPARATOR_LINE])

    if body_lines and body_lines[-1] == SEPARATOR_LINE:
        body_lines.pop()

    return "\n".join(header + body_lines) + "\n"


def _get_thread_monitor() -> FederalRegisterMonitor:
    """Provide or create a thread-local monitor for safe session reuse."""
    monitor = getattr(_THREAD_LOCAL, "monitor", None)
    if monitor is None:
        monitor = FederalRegisterMonitor()
        _THREAD_LOCAL.monitor = monitor
    return monitor


def fetch_page(
    monitor: FederalRegisterMonitor,
    page: int,
    per_page: int,
    order: str,
) -> Dict[str, Any]:
    """Fetch a single page of Federal Register results."""
    params = {
        "per_page": per_page,
        "order": order,
        "page": page,
    }
    response = monitor.session.get(
        monitor.BASE_URL,
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def process_range(
    index_range: Tuple[int, int],
    batch_size: int,
    temp_dir: Path,
    seen_urls: Set[str],
    lock: threading.Lock,
    order: str,
) -> Tuple[Tuple[int, int], Path, int]:
    """Worker entry point: fetch a range and persist thread-local results."""
    start_offset, end_offset = index_range
    monitor = _get_thread_monitor()
    page_size = max(1, min(batch_size, PAGE_SIZE_CAP))
    logger.info("Processing index range %s-%s with page size %s", start_offset, end_offset, page_size)

    new_entries: List[Dict[str, Any]] = []
    current_offset = start_offset

    while current_offset <= end_offset:
        page = current_offset // page_size + 1
        page_start_offset = (page - 1) * page_size

        try:
            raw_page = fetch_page(monitor, page=page, per_page=page_size, order=order)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to fetch page %s for range %s-%s: %s",
                page,
                start_offset,
                end_offset,
                exc,
            )
            current_offset = page_start_offset + page_size
            continue

        results = raw_page.get("results", [])
        if not results:
            logger.info(
                "No results returned for page %s (range %s-%s); stopping early.",
                page,
                start_offset,
                end_offset,
            )
            break

        parsed_items = list(monitor.parse({"results": results}))
        start_index = max(0, current_offset - page_start_offset)
        if start_index >= len(parsed_items):
            logger.debug(
                "Start index %s beyond parsed items (%s) on page %s; advancing offset.",
                start_index,
                len(parsed_items),
                page,
            )
            current_offset = page_start_offset + len(parsed_items)
            if len(parsed_items) < page_size:
                break
            continue

        remaining_offsets = end_offset - current_offset + 1
        available = len(parsed_items) - start_index
        take_count = min(available, remaining_offsets)
        if take_count <= 0:
            logger.debug("No items to take from page %s for range %s-%s; exiting loop.", page, start_offset, end_offset)
            break

        for index in range(start_index, start_index + take_count):
            item: NewsItem = parsed_items[index]
            url = item.url
            with lock:
                if url in seen_urls:
                    continue
                seen_urls.add(url)

            iso_timestamp = item.date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_entries.append(
                {
                    "title": item.title,
                    "source": item.source,
                    "url": url,
                    "summary": sanitize_summary(item.content),
                    "iso_timestamp": iso_timestamp,
                    "range_label": f"indices {start_offset}-{end_offset}",
                }
            )

        current_offset += take_count

        if take_count == 0:
            current_offset = page_start_offset + len(parsed_items)

        if len(parsed_items) < page_size:
            break

    temp_path = temp_dir / f"range_{start_offset}_{end_offset}.json"
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(new_entries, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("Failed to write temporary results for range %s-%s: %s", start_offset, end_offset, exc)
        raise

    logger.info(
        "Range %s-%s produced %s new entr%s",
        start_offset,
        end_offset,
        len(new_entries),
        "y" if len(new_entries) == 1 else "ies",
    )
    return index_range, temp_path, len(new_entries)


def load_thread_results(temp_files: Iterable[Path], tag: str) -> List[Dict[str, Any]]:
    """Load JSON results persisted by worker threads."""
    entries: List[Dict[str, Any]] = []
    for temp_path in temp_files:
        try:
            with temp_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except OSError as exc:
            logger.error("Failed to read temporary file %s: %s", temp_path, exc)
            continue
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in temporary file %s: %s", temp_path, exc)
            continue

        for record in payload:
            iso_timestamp = record.get("iso_timestamp")
            if not iso_timestamp:
                logger.debug("Skipping record with no timestamp in %s", temp_path)
                continue
            try:
                dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                logger.debug("Skipping record with malformed timestamp '%s' in %s", iso_timestamp, temp_path)
                continue

            entries.append(
                {
                    "title": record.get("title", "Untitled Federal Register notice"),
                    "source": record.get("source", "Federal Register"),
                    "url": record.get("url", ""),
                    "summary": record.get("summary", ""),
                    "datetime": dt,
                    "display_timestamp": dt.strftime("%Y-%m-%d %H:%M:%SZ"),
                    "batch_marker": record.get("range_label"),
                    "tag": tag,
                }
            )
    return entries


def merge_entries(
    existing: Iterable[Dict[str, Any]],
    new_entries: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Combine existing and new entries while preserving newest-first ordering."""
    combined: Dict[str, Dict[str, Any]] = {}
    for entry in existing:
        url = entry.get("url")
        if url:
            combined[url] = entry
    for entry in new_entries:
        url = entry.get("url")
        if not url or url in combined:
            continue
        combined[url] = entry
    merged = list(combined.values())
    merged.sort(key=lambda entry: entry["datetime"], reverse=True)
    return merged


def main() -> None:
    args = parse_args()
    configure_logging()

    try:
        index_ranges = parse_index_ranges(args.index_ranges)
    except ValueError as exc:
        logger.error("Invalid index ranges: %s", exc)
        return

    if args.num_threads <= 0:
        logger.error("Number of threads must be positive.")
        return

    if args.batch_size <= 0:
        logger.error("Batch size must be positive.")
        return

    output_file: Path = args.output_file

    existing_entries, existing_urls, existing_tag = load_existing_entries(output_file)
    seen_urls = set(existing_urls)
    lock = threading.Lock()

    temp_dir = Path(tempfile.mkdtemp(prefix="federal_register_parallel_"))
    logger.info("Using temporary directory %s for worker outputs", temp_dir)

    try:
        futures = []
        temp_paths: List[Path] = []

        max_workers = min(args.num_threads, len(index_ranges))
        logger.info(
            "Starting ThreadPoolExecutor with %s worker%s",
            max_workers,
            "" if max_workers == 1 else "s",
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for index_range in index_ranges:
                future = executor.submit(
                    process_range,
                    index_range,
                    args.batch_size,
                    temp_dir,
                    seen_urls,
                    lock,
                    "newest",
                )
                futures.append(future)

            for future in as_completed(futures):
                try:
                    _, temp_path, _ = future.result()
                    temp_paths.append(temp_path)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Range processing failed: %s", exc)

        new_entries = load_thread_results(temp_paths, tag=existing_tag or DEFAULT_TAG)
        logger.info("Collected %d new entr%s from worker outputs", len(new_entries), "y" if len(new_entries) == 1 else "ies")

        merged_entries = merge_entries(existing_entries, new_entries)
        logger.info(
            "Writing combined backlog with %d total entr%s to %s",
            len(merged_entries),
            "y" if len(merged_entries) == 1 else "ies",
            output_file,
        )

        backlog_text = format_backlog(merged_entries, tag=existing_tag or DEFAULT_TAG)

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(backlog_text, encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to write backlog to %s: %s", output_file, exc)
            return

        logger.info("Backlog update complete.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
