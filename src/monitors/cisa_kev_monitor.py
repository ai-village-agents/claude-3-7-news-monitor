"""
Concrete monitor for the CISA Known Exploited Vulnerabilities (KEV) catalog.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests

from .news_monitor import Monitor, NewsItem

logger = logging.getLogger(__name__)


class CisaKevMonitor(Monitor):
    """
    Monitor that ingests the CISA Known Exploited Vulnerabilities catalog and
    normalizes entries into `NewsItem` objects. Newly added vulnerabilities in
    the latest catalog release are highlighted for downstream consumers.
    """

    name = "cisa-kev"
    source_url = (
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    )
    timeout = 30

    def parse(self, response: requests.Response) -> Iterable[NewsItem]:
        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("Failed to decode CISA KEV response as JSON: %s", exc)
            return []

        if not isinstance(payload, dict):
            logger.error("Unexpected payload type from CISA KEV feed: %s", type(payload))
            return []

        vulnerabilities = payload.get("vulnerabilities") or []
        release_dt = self._parse_datetime(payload.get("dateReleased")) or datetime.now(
            tz=timezone.utc
        )
        latest_added_date = self._latest_date_added(vulnerabilities)

        for entry in vulnerabilities:
            item = self._vulnerability_to_item(
                entry=entry,
                catalog_release=release_dt,
                latest_added=latest_added_date,
            )
            if item:
                yield item

    def monitor_description(self) -> str:
        return (
            "Tracks the CISA Known Exploited Vulnerabilities catalog and flags the "
            "newest additions for rapid awareness."
        )

    def item_identity(self, item: NewsItem) -> str:
        cve_id = item.raw.get("cveID")
        if cve_id:
            return f"{self.name}:{cve_id}"
        return super().item_identity(item)

    def _vulnerability_to_item(
        self,
        entry: dict,
        catalog_release: datetime,
        latest_added: Optional[datetime],
    ) -> Optional[NewsItem]:
        cve_id = (entry.get("cveID") or "").strip()
        if not cve_id:
            logger.debug("Skipping vulnerability without CVE identifier: %s", entry)
            return None

        title_parts = [cve_id]
        vulnerability_name = (entry.get("vulnerabilityName") or "").strip()
        vendor = (entry.get("vendorProject") or "").strip()
        product = (entry.get("product") or "").strip()

        if vulnerability_name:
            title_parts.append(vulnerability_name)
        else:
            product_descriptor = " ".join(part for part in [vendor, product] if part)
            if product_descriptor:
                title_parts.append(product_descriptor)

        published_at = (
            self._parse_date_added(entry.get("dateAdded"))
            or catalog_release
            or datetime.now(tz=timezone.utc)
        )

        is_recent_addition = bool(
            latest_added and published_at.date() == latest_added.date()
        )
        if is_recent_addition:
            title_parts.insert(0, "[New]")

        notes = (entry.get("notes") or "").split(";")
        first_note = notes[0].strip() if notes else ""
        link = first_note if first_note.startswith("http") else ""
        if not link:
            link = f"https://nvd.nist.gov/vuln/detail/{cve_id}"

        summary_segments = []
        if is_recent_addition and latest_added:
            summary_segments.append(
                f"Added in latest CISA KEV release on {latest_added.date().isoformat()}."
            )

        short_description = (entry.get("shortDescription") or "").strip()
        if short_description:
            summary_segments.append(short_description)

        required_action = (entry.get("requiredAction") or "").strip()
        if required_action:
            summary_segments.append(f"Required action: {required_action}")

        due_date = (entry.get("dueDate") or "").strip()
        if due_date:
            summary_segments.append(f"Due date: {due_date}")

        ransomware_use = (entry.get("knownRansomwareCampaignUse") or "").strip()
        if ransomware_use and ransomware_use.lower() != "unknown":
            summary_segments.append(f"Known ransomware use: {ransomware_use}")

        summary = " ".join(summary_segments).strip()

        raw_entry = dict(entry)
        raw_entry["is_recent_addition"] = is_recent_addition
        raw_entry["catalogRelease"] = catalog_release.isoformat()

        return NewsItem(
            source=self.name,
            title=" | ".join(title_parts),
            link=link,
            published_at=published_at,
            summary=summary,
            raw=raw_entry,
        )

    def _latest_date_added(self, vulnerabilities: Iterable[dict]) -> Optional[datetime]:
        latest: Optional[datetime] = None
        for entry in vulnerabilities:
            candidate = self._parse_date_added(entry.get("dateAdded"))
            if not candidate:
                continue
            if latest is None or candidate > latest:
                latest = candidate
        return latest

    def _parse_date_added(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return self._parse_datetime(value)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            logger.debug("Unable to parse datetime value: %s", value)
            return None

