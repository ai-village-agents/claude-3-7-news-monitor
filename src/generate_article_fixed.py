#!/usr/bin/env python3

"""
Simple script to generate an HTML article and update index.html
"""

import os
import sys
import argparse
from datetime import datetime

def generate_article(title, summary, source_url):
    """Generate an HTML article and update the index"""
    # Create timestamp
    timestamp_iso = datetime.now().isoformat()
    timestamp_readable = datetime.now().strftime("%B %d, %Y %H:%M:%S UTC")
    
    # Create slug from title
    slug = title.lower().replace(" ", "-")
    for char in "!@#$%^&*()+={}[]|\\:;\"'<>,.?/":
        slug = slug.replace(char, "")
    slug = slug[:50]  # Limit length
    
    # Create directory for the article
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    article_dir = os.path.join(docs_dir, slug)
    
    os.makedirs(article_dir, exist_ok=True)
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="metadata">
        <p>Published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Source: <a href="{source_url}" target="_blank">{source_url}</a></p>
    </div>
    <div class="content">
        <p>{summary}</p>
    </div>
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
    </div>
</body>
</html>
"""
    
    # Write HTML file
    article_path = os.path.join(article_dir, "index.html")
    with open(article_path, "w") as f:
        f.write(html)
    
    print(f"Generated article: {article_path}")
    
    # Update index.html
    update_index(title, summary, timestamp_iso, timestamp_readable, slug)
    
    return article_path

def update_index(title, summary, timestamp_iso, timestamp_readable, slug):
    """Update the main index.html with a link to the new article"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(base_dir, "docs", "index.html")
    
    with open(index_path, "r") as f:
        content = f.read()
    
    # Find the news container
    container_marker = '<div id="news-container">'
    start_pos = content.find(container_marker) + len(container_marker)
    
    # Create new story HTML
    new_story = f"""
        <div class="story">
            <h2 class="story-title"><a href="{slug}/">{title}</a></h2>
            <p class="story-meta">Published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
            <p class="story-summary">{summary[:150]}{'...' if len(summary) > 150 else ''}</p>
            <p><a href="{slug}/">Read full article</a></p>
        </div>
"""
    
    # Insert at the beginning of the container
    updated_content = content[:start_pos] + new_story + content[start_pos:]
    
    with open(index_path, "w") as f:
        f.write(updated_content)
    
    print(f"Updated index.html with article: {title}")

def main():
    parser = argparse.ArgumentParser(description="Generate an article and update index.html")
    parser.add_argument("title", help="Article title")
    parser.add_argument("summary", help="Article summary")
    parser.add_argument("source_url", help="Source URL")
    
    args = parser.parse_args()
    
    try:
        generate_article(args.title, args.summary, args.source_url)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
