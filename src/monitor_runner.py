#!/usr/bin/env python3
"""
Command-line runner that executes the CISA KEV monitor, converts new findings
into articles for the GitHub Pages site, and pushes the updates via git.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

# Ensure the local src directory is importable when executed directly.
SRC_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from monitors.cisa_kev_monitor import CisaKevMonitor  # noqa: E402
from monitors.news_monitor import NewsItem, StorageBackend  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
DEFAULT_STATE_DIR = REPO_ROOT / ".monitor_state"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs"
DEFAULT_INDEX_FILE = DEFAULT_DOCS_DIR / "index.html"

LOGGER = logging.getLogger("monitor_runner")


@dataclass(frozen=True)
class StoryContext:
    """Information required to add a monitor discovery to index.html."""

    title: str
    href: str
    summary: str
    published_label: str
    discovered_label: str
    source_label: str


class JsonStateStorage(StorageBackend):
    """
    Simple JSON-backed storage that remembers which monitor items have already
    been published so reruns avoid generating duplicate articles.
    """

    def __init__(
        self,
        path: Path,
        identity_fn: Callable[[NewsItem], str],
    ) -> None:
        self.path = path
        self.identity_fn = identity_fn
        self._seen: set[str] = set()
        self._load()

    def has_item(self, item: NewsItem) -> bool:
        return self.identity_fn(item) in self._seen

    def persist(self, item: NewsItem) -> None:
        identity = self.identity_fn(item)
        if identity in self._seen:
            return
        now = datetime.now(timezone.utc).isoformat()
        record = {"id": identity, "title": item.title, "first_seen": now}
        self._seen.add(identity)
        self._save(record)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("State file %s is not valid JSON. Rebuilding cache.", self.path)
            return

        items = data if isinstance(data, list) else data.get("items", [])
        if not isinstance(items, list):
            LOGGER.warning("Unexpected JSON structure in %s. Rebuilding cache.", self.path)
            return

        for entry in items:
            identity = entry["id"] if isinstance(entry, dict) else entry
            if isinstance(identity, str) and identity:
                self._seen.add(identity)

    def _save(self, new_record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing: List[dict] = []
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                existing = payload if isinstance(payload, list) else payload.get("items", [])
                if not isinstance(existing, list):
                    existing = []
            except (OSError, json.JSONDecodeError):
                existing = []
        existing_map: dict[str, dict] = {}
        for entry in existing:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                existing_map[entry["id"]] = entry

        existing_map.setdefault(new_record["id"], new_record)
        serialisable = sorted(existing_map.values(), key=lambda item: item.get("id", ""))
        content = json.dumps({"items": serialisable}, indent=2, sort_keys=True)
        self.path.write_text(content + "\n", encoding="utf-8")


def format_datetime(dt: datetime) -> tuple[str, str]:
    """Return (ISO string, human-friendly string) in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    iso_value = dt_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    readable = dt_utc.strftime("%B %d, %Y %H:%M UTC")
    return iso_value, readable


def slugify(item: NewsItem) -> str:
    base = item.raw.get("cveID") if isinstance(item.raw, dict) else None
    if not base:
        base = item.title or item.identity()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    slug = slug or "kev-item"
    return f"cisa-kev-{slug}"


def discover_sources(item: NewsItem) -> List[str]:
    sources: List[str] = []
    notes = item.raw.get("notes") if isinstance(item.raw, dict) else None
    if isinstance(notes, str):
        for part in notes.split(";"):
            candidate = part.strip()
            if candidate.startswith("http"):
                sources.append(candidate)
    elif isinstance(notes, Iterable):
        for part in notes:
            if isinstance(part, str) and part.strip().startswith("http"):
                sources.append(part.strip())
    if item.link and item.link not in sources:
        sources.append(item.link)
    return sources or ["https://www.cisa.gov/known-exploited-vulnerabilities-catalog"]


def build_article_html(item: NewsItem, discovered_at: datetime) -> str:
    iso_published, readable_published = format_datetime(item.published_at)
    iso_discovered, readable_discovered = format_datetime(discovered_at)

    title = html.escape(item.title or item.raw.get("cveID", "CISA KEV Update"))
    summary_text = (item.summary or item.raw.get("shortDescription") or "").strip()
    summary_html = ""
    if summary_text:
        escaped = "<br>".join(html.escape(line) for line in summary_text.splitlines() if line)
        summary_html = f"<p>{escaped}</p>"

    details: List[tuple[str, str]] = []
    raw = item.raw if isinstance(item.raw, dict) else {}
    for label, key in [
        ("CVE ID", "cveID"),
        ("Vendor / Project", "vendorProject"),
        ("Product", "product"),
        ("Required Action", "requiredAction"),
        ("Due Date", "dueDate"),
        ("Known Ransomware Campaign Use", "knownRansomwareCampaignUse"),
        ("Catalog Release", "catalogRelease"),
    ]:
        value = raw.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned.lower() != "unknown":
                details.append((label, cleaned))

    detail_rows = ""
    if details:
        rows = "\n".join(
            f"                <tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
            for label, value in details
        )
        detail_rows = (
            "            <section class=\"detail-table\">\n"
            "                <h2>Key Details</h2>\n"
            "                <table>\n"
            "                    <tbody>\n"
            f"{rows}\n"
            "                    </tbody>\n"
            "                </table>\n"
            "            </section>\n"
        )

    sources = discover_sources(item)
    sources_html = "\n".join(
        f'                <li><a href="{html.escape(src)}" target="_blank" rel="noopener noreferrer">{html.escape(src)}</a></li>'
        for src in sources
    )

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | Claude 3.7 News Monitor</title>
    <link rel="stylesheet" href="styles.css">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        header, footer {{ background: #0d1b2a; color: #fff; padding: 20px 0; }}
        .container {{ width: 90%; max-width: 900px; margin: 0 auto; }}
        main.article {{ padding: 30px 0; }}
        .meta {{ color: #555; font-size: 0.9em; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ text-align: left; border-bottom: 1px solid #ddd; padding: 8px; }}
        .sources ul {{ list-style: disc; padding-left: 20px; }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>Claude 3.7 News Monitor</h1>
            <p>Realtime CISA KEV intelligence feed</p>
            <nav>
                <a href="index.html" style="color: #fff; text-decoration: underline;">Back to latest stories</a>
            </nav>
        </div>
    </header>
    <main class="container article">
        <article>
            <h1>{title}</h1>
            <p class="meta">
                Source publication: <time datetime="{iso_published}">{readable_published}</time><br>
                Monitor discovery: <time datetime="{iso_discovered}">{readable_discovered}</time> (UTC)
            </p>
{summary_html or ''}
{detail_rows or ''}
            <section class="sources">
                <h2>Source Links</h2>
                <ul>
{sources_html}
                </ul>
            </section>
        </article>
    </main>
    <footer>
        <div class="container">
            <p>&copy; {datetime.now().year} Claude 3.7 News Monitor &mdash; Generated automatically for first-to-publish proof.</p>
        </div>
    </footer>
</body>
</html>
"""
    return body


def build_story_context(item: NewsItem, article_filename: str, discovered_at: datetime) -> StoryContext:
    _, readable_published = format_datetime(item.published_at)
    _, readable_discovered = format_datetime(discovered_at)
    source_label = "CISA Known Exploited Vulnerabilities Catalog"

    short_desc = (item.summary or item.raw.get("shortDescription") or "").strip()
    required = item.raw.get("requiredAction", "").strip() if isinstance(item.raw, dict) else ""
    due_date = item.raw.get("dueDate", "").strip() if isinstance(item.raw, dict) else ""

    description_bits: List[str] = []
    if short_desc:
        description_bits.append(short_desc)
    if required:
        description_bits.append(f"Required action: {required}")
    if due_date:
        description_bits.append(f"Due date: {due_date}")
    description_bits.append(f"Monitor discovery timestamp: {readable_discovered}")

    summary = " ".join(bit for bit in description_bits if bit)
    summary = summary or "Automated KEV monitor detected a newly listed vulnerability."

    return StoryContext(
        title=item.title or item.raw.get("cveID", "CISA KEV Update"),
        href=article_filename,
        summary=summary,
        published_label=readable_published,
        discovered_label=readable_discovered,
        source_label=source_label,
    )


def update_index(index_path: Path, stories: Sequence[StoryContext]) -> None:
    if not index_path.exists():
        raise FileNotFoundError(f"index file not found: {index_path}")

    content = index_path.read_text(encoding="utf-8")
    timestamp_text = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    content, updated = re.subn(
        r"(Last updated:\s*)([^<]+)",
        rf"\1{timestamp_text}",
        content,
        count=1,
    )
    if updated == 0:
        LOGGER.warning("Did not find 'Last updated' marker in %s", index_path)

    story_blocks = []
    for story in stories:
        block = (
            "    <div class=\"story\">\n"
            "        <div class=\"story-title\">\n"
            f"            <a href=\"{html.escape(story.href)}\">{html.escape(story.title)}</a> "
            "<span class=\"breaking\">BREAKING</span>\n"
            "        </div>\n"
            "        <div class=\"story-meta\">\n"
            f"            Published: {html.escape(story.published_label)} | "
            f"Source: {html.escape(story.source_label)} | "
            f"Discovered: {html.escape(story.discovered_label)}\n"
            "        </div>\n"
            "        <div class=\"story-description\">\n"
            f"            {html.escape(story.summary)}\n"
            "        </div>\n"
            "    </div>\n"
        )
        story_blocks.append(block)

    insertion_anchor = content.find("<h2>Latest Stories</h2>")
    if insertion_anchor == -1:
        raise ValueError("Unable to locate the 'Latest Stories' section in index.html.")
    insertion_point = content.find('<div class="story">', insertion_anchor)
    if insertion_point == -1:
        insertion_point = content.find("</main>", insertion_anchor)
        if insertion_point == -1:
            insertion_point = content.find("</body>", insertion_anchor)
    prefix = content[:insertion_point]
    suffix = content[insertion_point:]
    new_content = prefix + "\n" + "\n".join(story_blocks) + "\n" + suffix
    index_path.write_text(new_content, encoding="utf-8")


def write_article(doc_dir: Path, slug: str, html_body: str) -> Path:
    doc_dir.mkdir(parents=True, exist_ok=True)
    article_path = doc_dir / f"{slug}.html"
    counter = 1
    while article_path.exists():
        article_path = doc_dir / f"{slug}-{counter}.html"
        counter += 1
    article_path.write_text(html_body, encoding="utf-8")
    return article_path


def run_git_commands(paths: Iterable[Path], message: str, repo_root: Path) -> None:
    git_paths: List[str] = []
    for path in paths:
        try:
            git_paths.append(str(path.resolve().relative_to(repo_root.resolve())))
        except ValueError:
            git_paths.append(str(path))

    def run_git(args: List[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    add_result = run_git(["add", *git_paths])
    if add_result.returncode != 0:
        raise RuntimeError(f"git add failed: {add_result.stderr.strip()}")

    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_root,
        check=False,
    )
    if diff_result.returncode == 0:
        LOGGER.info("No staged changes to commit.")
        return

    commit_result = run_git(["commit", "-m", message])
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")

    push_result = run_git(["push"])
    if push_result.returncode != 0:
        raise RuntimeError(f"git push failed: {push_result.stderr.strip() or push_result.stdout.strip()}")

    LOGGER.info("Changes committed and pushed successfully.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CISA KEV monitor and publish new items.")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_DIR / "cisa-kev-seen.json")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--index-file", type=Path, default=DEFAULT_INDEX_FILE)
    parser.add_argument("--no-git", action="store_true", help="Skip git commit and push steps.")
    parser.add_argument("--verbose", action="store_true", help="Increase logging verbosity.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    monitor = CisaKevMonitor()
    storage = JsonStateStorage(args.state_file, identity_fn=monitor.item_identity)
    monitor.storage = storage

    try:
        new_items = monitor.run_once()
    except Exception as exc:
        LOGGER.error("Monitor execution failed: %s", exc)
        return 1

    if not new_items:
        LOGGER.info("No new CISA KEV items detected.")
        return 0

    discovered_items: List[tuple[NewsItem, datetime, Path]] = []
    stories: List[StoryContext] = []
    for item in new_items:
        discovered_at = datetime.now(timezone.utc)
        slug = slugify(item)
        article_html = build_article_html(item, discovered_at)
        article_path = write_article(args.docs_dir, slug, article_html)
        story = build_story_context(item, article_path.name, discovered_at)
        stories.append(story)
        discovered_items.append((item, discovered_at, article_path))
        LOGGER.info("Article generated for %s -> %s", story.title, article_path)

    update_index(args.index_file, stories)
    LOGGER.info("index.html updated with %d new stor%s.", len(stories), "y" if len(stories) == 1 else "ies")

    if not args.no_git:
        commit_ids = [
            item.raw.get("cveID", item.title).strip()
            for item, _, _ in discovered_items
            if isinstance(item.raw, dict)
        ]
        commit_suffix = ", ".join(commit_ids) if commit_ids else f"{len(discovered_items)} item(s)"
        commit_message = f"Add CISA KEV update(s): {commit_suffix}"
        commit_paths = [args.index_file, args.state_file] + [path for _, _, path in discovered_items]
        try:
            run_git_commands(commit_paths, commit_message, REPO_ROOT)
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            return 1
    else:
        LOGGER.info("Git steps skipped (--no-git supplied).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
