#!/usr/bin/env python3

import argparse
import os
import sys
from datetime import datetime
import html

def main():
    parser = argparse.ArgumentParser(description="Generate a news article and add it to index.html")
    parser.add_argument("title", help="Article title")
    parser.add_argument("content", help="Article content")
    parser.add_argument("sources", nargs='+', help="URLs to source(s)")
    args = parser.parse_args()
    
    # Generate HTML article
    current_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    readable_time = datetime.utcnow().strftime("%B %d, %Y %H:%M UTC")
    
    title = html.escape(args.title)
    content = args.content
    sources = args.sources
    
    # Create article HTML
    article_html = f"""
        <div class="article">
            <h2>{title}</h2>
            <p class="timestamp">Posted: <time datetime="{current_time}">{readable_time}</time></p>
            <p>{content}</p>
            <p>Sources:</p>
            <ul>
    """
    
    for source in sources:
        escaped_source = html.escape(source)
        article_html += f'                <li><a href="{escaped_source}" target="_blank" rel="noopener noreferrer">{escaped_source}</a></li>\n'
    
    article_html += """
            </ul>
        </div>
    """
    
    # Read current index.html
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    index_path = os.path.join(docs_dir, "index.html")
    
    with open(index_path, 'r') as f:
        content = f.read()
    
    # Find insertion point (after main opening tag)
    container_marker = '<main id="news-container">'
    insertion_point = content.find(container_marker) + len(container_marker)
    
    # Insert article
    new_content = content[:insertion_point] + article_html + content[insertion_point:]
    
    # Write updated index.html
    with open(index_path, 'w') as f:
        f.write(new_content)
    
    print(f"Article '{args.title}' added to index.html with timestamp {readable_time}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
