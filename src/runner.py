#!/usr/bin/env python3
"""
Simple runner script to execute monitors and publish findings.
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitors.cisa_kev_monitor import CisaKevMonitor
from src.monitors.news_monitor import NewsItem

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def create_article_html(item: NewsItem, slug: str) -> Path:
    """Generate HTML article page for a news item."""
    article_dir = DOCS_DIR / slug
    article_dir.mkdir(exist_ok=True, parents=True)
    
    article_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Published: {datetime.now().strftime("%B %d, %Y %H:%M:%S UTC")}</p>
        <p>Source: <a href="{item.link}" target="_blank">{item.source}</a></p>
    </div>
    <div class="content">
        <p>{item.summary}</p>
        
        <h2>Details:</h2>
        <ul>
            <li>CVE ID: {item.raw.get('cveID', 'N/A')}</li>
            <li>Vendor/Project: {item.raw.get('vendorProject', 'N/A')}</li>
            <li>Product: {item.raw.get('product', 'N/A')}</li>
            <li>Date Added to KEV: {item.raw.get('dateAdded', 'N/A')}</li>
            <li>Required Action: {item.raw.get('requiredAction', 'N/A')}</li>
            <li>Due Date: {item.raw.get('dueDate', 'N/A')}</li>
        </ul>
    </div>
    <p><a href="../">← Back to all news</a></p>
</body>
</html>
"""
    
    article_path = article_dir / "index.html"
    with open(article_path, "w") as f:
        f.write(article_html)
        
    logger.info(f"Created article at {article_path}")
    return article_path


def update_index_html(new_articles: list[tuple[str, Path]]) -> None:
    """Update the main index.html with new article links."""
    index_path = DOCS_DIR / "index.html"
    
    # Create a basic index.html if it doesn't exist
    if not index_path.exists():
        with open(index_path, "w") as f:
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude 3.7 News Monitor</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1, h2 { color: #333; }
        .story { margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
    </style>
</head>
<body>
    <h1>Claude 3.7 News Monitor</h1>
    <p>Breaking news detected and published automatically.</p>
    <div id="news-container">
    </div>
</body>
</html>""")
    
    # Read the current index
    with open(index_path, "r") as f:
        content = f.read()
    
    # Find insertion point
    insert_marker = '<div id="news-container">'
    insert_pos = content.find(insert_marker) + len(insert_marker)
    
    # Create article entries
    new_entries = ""
    timestamp = datetime.now().strftime("%B %d, %Y %H:%M:%S UTC")
    
    for title, article_path in new_articles:
        rel_path = os.path.relpath(article_path.parent, DOCS_DIR)
        entry = f"""
        <div class="story">
            <h2><a href="{rel_path}/">{title}</a></h2>
            <p>Published: {timestamp}</p>
            <p><a href="{rel_path}/">Read full article</a></p>
        </div>
        """
        new_entries += entry
    
    # Insert at the beginning of the news container
    updated_content = content[:insert_pos] + new_entries + content[insert_pos:]
    
    # Write back the updated content
    with open(index_path, "w") as f:
        f.write(updated_content)
        
    logger.info("Updated index.html with new articles")


def git_publish(message: str) -> bool:
    """Commit and push changes to GitHub."""
    try:
        subprocess.run(["git", "add", "."], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True)
        logger.info("Successfully pushed changes to GitHub")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run monitors and publish findings")
    parser.add_argument("--no-git", action="store_true", help="Skip git operations")
    args = parser.parse_args()
    
    # Run CISA KEV monitor
    monitor = CisaKevMonitor()
    new_items = monitor.run_once()
    
    if not new_items:
        logger.info("No new items found")
        return
    
    logger.info(f"Found {len(new_items)} new items")
    
    # Create articles
    new_articles = []
    for item in new_items:
        # Create slug from CVE ID
        cve_id = item.raw.get("cveID", "")
        if cve_id:
            slug = f"cisa-kev-{cve_id.lower()}"
        else:
            # Fallback to title-based slug
            slug = item.title.lower().replace(" ", "-")
            for char in "!@#$%^&*()+={}[]|\\:;\"'<>,.?/":
                slug = slug.replace(char, "")
        
        # Create the article
        article_path = create_article_html(item, slug)
        new_articles.append((item.title, article_path))
    
    # Update index
    update_index_html(new_articles)
    
    # Commit and push changes
    if not args.no_git:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"Add {len(new_articles)} new CISA KEV articles - {timestamp}"
        git_publish(commit_msg)


if __name__ == "__main__":
    main()
