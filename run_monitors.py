#!/usr/bin/env python3
"""
Run one or more news monitors in parallel and print their results.
"""

from __future__ import annotations

import argparse
import logging
import time
import traceback
from datetime import datetime, timezone
from multiprocessing import get_context
from pathlib import Path
from typing import Dict, List, Tuple

from scripts.monitors import NewsItem
from scripts.monitors.bank_of_england import BankOfEnglandMonitor
from scripts.monitors.canada_gov import CanadaGovMonitor
from scripts.monitors.cisa_kev import CISAKEVMonitor
from scripts.monitors.financial_regulators import FinancialRegulatorsMonitor
from scripts.monitors.international_courts import InternationalCourtsMonitor
from scripts.monitors.uk_gov import UKGovMonitor
from scripts.monitors.usgs_earthquakes import USGSEarthquakeMonitor


DEFAULT_TIMEOUT = 120

MONITOR_CLASSES = {
    "bank_of_england": BankOfEnglandMonitor,
    "canada_gov": CanadaGovMonitor,
    "cisa_kev": CISAKEVMonitor,
    "financial_regulators": FinancialRegulatorsMonitor,
    "international_courts": InternationalCourtsMonitor,
    "uk_gov": UKGovMonitor,
    "usgs_earthquakes": USGSEarthquakeMonitor,
}

MONITOR_LABELS = {
    "bank_of_england": "Bank of England",
    "canada_gov": "Government of Canada",
    "cisa_kev": "CISA Known Exploited Vulnerabilities",
    "financial_regulators": "Financial Regulators",
    "international_courts": "International Courts",
    "uk_gov": "UK Government",
    "usgs_earthquakes": "USGS Earthquakes",
}

logger = logging.getLogger("run_monitors")


def setup_logging() -> Path:
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"monitor_run_{timestamp}.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logger.info("Logging initialized. Writing to %s", log_path)
    return log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one or more news monitors in parallel.",
        epilog="Available monitors: " + ", ".join(sorted(MONITOR_CLASSES.keys())),
    )
    parser.add_argument(
        "--monitor",
        choices=["all"] + sorted(MONITOR_CLASSES.keys()),
        default="all",
        help="Monitor to run (default: all).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for each monitor before timing out.",
    )
    return parser.parse_args()


def _run_monitor_worker(monitor_key: str) -> Dict[str, object]:
    try:
        monitor_cls = MONITOR_CLASSES[monitor_key]
    except KeyError:
        return {
            "monitor": monitor_key,
            "error": f"Unknown monitor '{monitor_key}'",
        }

    try:
        monitor = monitor_cls()
        items = monitor.run()
        return {
            "monitor": monitor_key,
            "items": items,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "monitor": monitor_key,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def run_monitors_parallel(
    monitor_keys: List[str],
    timeout: int,
) -> Tuple[Dict[str, List[NewsItem]], Dict[str, str], bool]:
    ctx = get_context("spawn")
    cpu_available = ctx.cpu_count() or len(monitor_keys)
    process_count = max(1, min(len(monitor_keys), cpu_available))
    logger.info(
        "Running %d monitor(s) with %d worker process(es)",
        len(monitor_keys),
        process_count,
    )

    pool = ctx.Pool(processes=process_count, maxtasksperchild=1)
    async_results = {}
    start_times = {}
    for key in monitor_keys:
        async_results[key] = pool.apply_async(_run_monitor_worker, (key,))
        start_times[key] = time.monotonic()

    successes: Dict[str, List[NewsItem]] = {}
    failures: Dict[str, str] = {}
    had_timeout = False

    try:
        while async_results:
            completed_any = False
            for key, async_result in list(async_results.items()):
                if async_result.ready():
                    payload = async_result.get()
                    async_results.pop(key, None)
                    start_times.pop(key, None)
                    completed_any = True

                    error_message = payload.get("error")
                    if error_message:
                        failures[key] = str(error_message)
                        trace = payload.get("traceback")
                        if trace:
                            logger.error("Monitor %s failed:\n%s", key, trace)
                        else:
                            logger.error("Monitor %s failed: %s", key, error_message)
                        continue

                    items = payload.get("items", []) or []
                    successes[key] = list(items)
                    logger.info("Monitor %s returned %d item(s)", key, len(items))
                else:
                    elapsed = time.monotonic() - start_times[key]
                    if timeout and elapsed > timeout:
                        failures[key] = f"Timed out after {timeout} seconds"
                        had_timeout = True
                        logger.error(
                            "Monitor %s timed out after %d seconds", key, timeout
                        )
                        async_results.pop(key, None)
                        start_times.pop(key, None)
            if async_results and not completed_any:
                time.sleep(0.2)
    finally:
        if had_timeout:
            pool.terminate()
        else:
            pool.close()
        pool.join()

    return successes, failures, had_timeout


def _format_timestamp(data: datetime) -> str:
    timestamp = data
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.strftime("%Y-%m-%d %H:%M:%SZ")


def display_results(results: Dict[str, List[NewsItem]]) -> None:
    for key in sorted(results.keys(), key=lambda name: MONITOR_LABELS.get(name, name)):
        items = results[key]
        label = MONITOR_LABELS.get(key, key)

        print("=" * 80)
        print(f"{label} ({len(items)} item{'s' if len(items) != 1 else ''})")
        print("=" * 80)

        if not items:
            print("No items found.\n")
            continue

        sorted_items = sorted(items, key=lambda item: item.date, reverse=True)
        for item in sorted_items:
            status = "!!! BREAKING !!!" if item.is_breaking else "Update"
            timestamp = _format_timestamp(item.date)
            print(f"[{status}] {timestamp} | {item.title}")
            print(f"Source: {item.source}")
            print(f"URL: {item.url}")
            if item.content:
                print(item.content)
            print("-" * 80)
        print()


def main() -> None:
    args = parse_args()
    log_path = setup_logging()

    monitor_keys = (
        list(MONITOR_CLASSES.keys())
        if args.monitor == "all"
        else [args.monitor]
    )

    logger.info("Selected monitors: %s", ", ".join(monitor_keys))

    try:
        results, failures, had_timeout = run_monitors_parallel(
            monitor_keys=monitor_keys,
            timeout=args.timeout,
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        print("\nRun aborted by user.")
        return

    if results:
        display_results(results)
    else:
        print("No monitor results to display.")

    if failures:
        print("Some monitors failed:")
        for key, reason in failures.items():
            label = MONITOR_LABELS.get(key, key)
            print(f"- {label}: {reason}")

    print(f"Logs written to {log_path}")

    if failures or had_timeout:
        exit_code = 1
    else:
        exit_code = 0
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
