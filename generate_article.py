#!/usr/bin/env python3
"""
Utility to convert a markdown news article into HTML and inject it into docs/index.html.

The markdown file is expected to begin with YAML-like frontmatter that at minimum
defines `title`, `timestamp`, and `sources` (as a list). The body of the markdown
is rendered to HTML and inserted at the top of the news container in the index.
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import indent
from typing import Dict, List, Tuple


class ArticleGenerationError(Exception):
    """Raised when article generation or insertion fails."""


def read_markdown(path: Path) -> str:
    if not path.exists():
        raise ArticleGenerationError(f"Markdown file not found: {path}")
    if not path.is_file():
        raise ArticleGenerationError(f"Markdown path is not a file: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArticleGenerationError(f"Failed to read markdown file: {exc}") from exc


def parse_frontmatter(raw_text: str) -> Tuple[Dict[str, object], str]:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ArticleGenerationError(
            "Markdown file is missing the opening frontmatter delimiter '---'."
        )

    closing_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_index = idx
            break
    if closing_index is None:
        raise ArticleGenerationError(
            "Frontmatter is not closed with the delimiter '---'."
        )

    front_lines = lines[1:closing_index]
    body_lines = lines[closing_index + 1 :]

    metadata: Dict[str, object] = {}
    current_list_key: str | None = None

    for raw_line in front_lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if line.lstrip().startswith("#"):
            raise ArticleGenerationError(
                f"Unexpected character in frontmatter: '{line.strip()}'"
            )

        if line.startswith((" ", "\t")):
            stripped = line.strip()
            if stripped.startswith("- "):
                if current_list_key is None:
                    raise ArticleGenerationError(
                        f"List item without preceding key in frontmatter: '{line}'"
                    )
                target = metadata.get(current_list_key)
                if not isinstance(target, list):
                    raise ArticleGenerationError(
                        f"Frontmatter key '{current_list_key}' does not accept list items."
                    )
                target.append(stripped[2:].strip())
                continue
            raise ArticleGenerationError(
                f"Unsupported indentation in frontmatter: '{line}'"
            )

        if ":" not in line:
            raise ArticleGenerationError(f"Invalid frontmatter entry: '{line}'")

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ArticleGenerationError("Frontmatter keys cannot be empty.")

        if value:
            metadata[key] = value
            current_list_key = None
        else:
            metadata[key] = []
            current_list_key = key

    required_keys = ("title", "timestamp", "sources")
    for key in required_keys:
        if key not in metadata:
            raise ArticleGenerationError(f"Missing required frontmatter field: '{key}'")

    sources = metadata.get("sources")
    if isinstance(sources, str):
        cleaned = sources.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]
        candidates = [
            item.strip().strip("'\"") for item in cleaned.split(",") if item.strip().strip("'\"")
        ] or ([cleaned] if cleaned and "," not in cleaned else [])
        if not candidates:
            raise ArticleGenerationError(
                "Frontmatter 'sources' string must contain at least one entry."
            )
        metadata["sources"] = candidates
        sources = metadata["sources"]
    if not isinstance(sources, list) or not sources:
        raise ArticleGenerationError(
            "Frontmatter 'sources' field must be a non-empty list."
        )

    body = "\n".join(body_lines).lstrip()
    if not body:
        raise ArticleGenerationError("Markdown content is empty after frontmatter.")

    return metadata, body


def convert_markdown_to_html(markdown_body: str) -> str:
    try:
        import markdown  # type: ignore
    except ImportError as exc:
        raise ArticleGenerationError(
            "Missing dependency 'markdown'. Install it with 'pip install markdown'."
        ) from exc

    try:
        html_body = markdown.markdown(markdown_body, extensions=["extra"])
    except Exception:
        html_body = markdown.markdown(markdown_body)

    cleaned = html_body.strip()
    if not cleaned:
        raise ArticleGenerationError("Rendered HTML content is empty.")
    return cleaned


def format_timestamp(timestamp_raw: str) -> Tuple[str, str]:
    iso_value = timestamp_raw.strip()
    if not iso_value:
        raise ArticleGenerationError("Timestamp value in frontmatter is empty.")

    normalised = iso_value
    if iso_value.upper().endswith("Z"):
        normalised = iso_value[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise ArticleGenerationError(
            f"Timestamp is not a valid ISO-8601 value: '{iso_value}'"
        ) from exc

    date_part = f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    show_time = any([dt.hour, dt.minute, dt.second])

    tz_suffix = ""
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        offset = dt.utcoffset()
        if offset == timedelta(0):
            tz_suffix = "UTC"
        else:
            tz_suffix = dt.tzname() or ""

    if show_time:
        time_part = dt.strftime("%H:%M")
        readable = f"{date_part} {time_part}".strip()
        if tz_suffix:
            readable = f"{readable} {tz_suffix}".strip()
    else:
        readable = date_part

    return iso_value, readable


def build_article_html(
    metadata: Dict[str, object], content_html: str, iso_timestamp: str, readable_ts: str
) -> str:
    title = html.escape(str(metadata["title"]))
    escaped_iso = html.escape(iso_timestamp, quote=True)
    escaped_readable = html.escape(readable_ts)

    sources = metadata["sources"]
    if not isinstance(sources, list) or not all(isinstance(src, str) for src in sources):
        raise ArticleGenerationError("Frontmatter 'sources' must be a list of strings.")

    article_lines: List[str] = [
        "        <div class=\"article\">",
        f"            <h2>{title}</h2>",
        (
            f"            <p class=\"timestamp\">Posted: "
            f"<time datetime=\"{escaped_iso}\">{escaped_readable}</time></p>"
        ),
    ]

    for line in indent(content_html, "            ").splitlines():
        article_lines.append(line)

    article_lines.append("            <p>Sources:</p>")
    article_lines.append("            <ul>")
    for src in sources:
        escaped_src = html.escape(src.strip())
        if not escaped_src:
            raise ArticleGenerationError("Encountered an empty source entry.")
        article_lines.append(
            "                "
            f"<li><a href=\"{escaped_src}\" target=\"_blank\" rel=\"noopener noreferrer\">"
            f"{escaped_src}</a></li>"
        )
    article_lines.append("            </ul>")
    article_lines.append("        </div>\n")

    return "\n".join(article_lines)


def inject_article(index_path: Path, article_html: str, iso_timestamp: str) -> None:
    if not index_path.exists():
        raise ArticleGenerationError(f"Index file not found: {index_path}")
    if not index_path.is_file():
        raise ArticleGenerationError(f"Index path is not a file: {index_path}")

    try:
        index_content = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArticleGenerationError(f"Failed to read index file: {exc}") from exc

    container_marker = '<main id="news-container"'
    container_pos = index_content.find(container_marker)
    if container_pos == -1:
        raise ArticleGenerationError(
            "Unable to locate the news container '<main id=\"news-container\">' in index.html."
        )

    if f'datetime="{iso_timestamp}"' in index_content:
        raise ArticleGenerationError(
            "An article with the same timestamp already exists in the index."
        )

    insertion_point = index_content.find('<div class="article"', container_pos)
    if insertion_point == -1:
        insertion_point = index_content.find("</main>", container_pos)
        if insertion_point == -1:
            raise ArticleGenerationError(
                "Unable to determine where to insert the new article within the news container."
            )
    newline_index = index_content.rfind("\n", container_pos, insertion_point)
    if newline_index != -1:
        insertion_point = newline_index + 1

    updated_content = (
        index_content[:insertion_point] + article_html + index_content[insertion_point:]
    )

    try:
        index_path.write_text(updated_content, encoding="utf-8")
    except OSError as exc:
        raise ArticleGenerationError(f"Failed to write updated index file: {exc}") from exc


def process_article(markdown_path: Path, index_path: Path) -> None:
    raw_markdown = read_markdown(markdown_path)
    metadata, markdown_body = parse_frontmatter(raw_markdown)
    iso_timestamp, readable_timestamp = format_timestamp(str(metadata["timestamp"]))
    content_html = convert_markdown_to_html(markdown_body)
    article_html = build_article_html(metadata, content_html, iso_timestamp, readable_timestamp)
    inject_article(index_path, article_html, iso_timestamp)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a markdown news article to HTML and inject it into docs/index.html."
    )
    parser.add_argument(
        "markdown_file",
        type=Path,
        help="Path to the markdown file containing the article and frontmatter.",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("docs/index.html"),
        help="Path to the index HTML file to update (default: docs/index.html).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        process_article(args.markdown_file, args.index)
    except ArticleGenerationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # Guard against unexpected errors with context.
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Article from '{args.markdown_file}' successfully added to '{args.index}'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
