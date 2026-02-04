#!/usr/bin/env python3
"""
Main script to run all monitors and publish findings to GitHub Pages.
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.monitors.cisa_kev_monitor import CisaKevMonitor
from src.monitors.usgs_monitor import USGSEarthquakeMonitor
from src.monitors.noaa_swpc_monitor import NOAASWPCMonitor
from src.monitors.sec_edgar_monitor import SECEdgarMonitor
from src.monitors.news_monitor import Monitor, NewsItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("monitor_runner")

DOCS_DIR = project_root / "docs"


def create_slug(item: NewsItem) -> str:
    """Create a URL-friendly slug for the news item."""
    # For CISA KEV items
    if item.source == "cisa-kev" and "cveID" in item.raw:
        return f"cisa-kev-{item.raw['cveID'].lower()}"
    
    # For USGS earthquakes
    if item.source == "usgs-earthquakes" and "id" in item.raw:
        return f"earthquake-{item.raw['id']}"
    
    # For NOAA SWPC alerts
    if item.source == "noaa-swpc" and "product" in item.raw:
        product = item.raw["product"].lower().replace(" ", "-")
        timestamp = item.published_at.strftime("%Y%m%d-%H%M")
        return f"space-weather-{product}-{timestamp}"
    
    # For SEC EDGAR filings
    if item.source == "sec-edgar" and "company" in item.raw and "form_type" in item.raw:
        company = item.raw["company"].lower().replace(" ", "-")
        form_type = item.raw["form_type"].lower().replace(" ", "-")
        timestamp = item.published_at.strftime("%Y%m%d")
        return f"sec-{company}-{form_type}-{timestamp}"
    
    # Default fallback: use title
    title_slug = item.title.lower()
    for char in "!@#$%^&*()+={}[]|\\:;\"'<>,.?/":
        title_slug = title_slug.replace(char, "")
    title_slug = title_slug.replace(" ", "-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{item.source}-{title_slug[:30]}-{timestamp}"


def create_article_html(item: NewsItem) -> Optional[Path]:
    """Generate an HTML article for a news item."""
    try:
        slug = create_slug(item)
        article_dir = DOCS_DIR / slug
        article_dir.mkdir(exist_ok=True, parents=True)
        
        # Convert timestamp to readable format
        timestamp_iso = datetime.now().isoformat()
        timestamp_readable = datetime.now().strftime("%B %d, %Y %H:%M:%S UTC")
        
        # Build HTML content based on source type
        if item.source == "cisa-kev":
            article_html = create_cisa_kev_article_html(item, timestamp_iso, timestamp_readable)
        elif item.source == "usgs-earthquakes":
            article_html = create_usgs_article_html(item, timestamp_iso, timestamp_readable)
        elif item.source == "noaa-swpc":
            article_html = create_noaa_article_html(item, timestamp_iso, timestamp_readable)
        elif item.source == "sec-edgar":
            article_html = create_sec_article_html(item, timestamp_iso, timestamp_readable)
        else:
            article_html = create_generic_article_html(item, timestamp_iso, timestamp_readable)
        
        article_path = article_dir / "index.html"
        with open(article_path, "w") as f:
            f.write(article_html)
        
        logger.info(f"Created article at {article_path}")
        return article_path
    
    except Exception as e:
        logger.error(f"Error generating article for {item.title}: {e}")
        return None


def create_generic_article_html(item: NewsItem, timestamp_iso: str, timestamp_readable: str) -> str:
    """Create a generic article HTML."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Detected and published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Original source: <a href="{item.link}" target="_blank">{item.source}</a></p>
    </div>
    <div class="content">
        <p>{item.summary}</p>
    </div>
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
    </div>
</body>
</html>"""


def create_cisa_kev_article_html(item: NewsItem, timestamp_iso: str, timestamp_readable: str) -> str:
    """Create a CISA KEV-specific article HTML."""
    # Extract fields from raw data
    cve_id = item.raw.get("cveID", "N/A")
    vendor = item.raw.get("vendorProject", "N/A")
    product = item.raw.get("product", "N/A")
    vuln_name = item.raw.get("vulnerabilityName", "N/A")
    description = item.raw.get("shortDescription", "N/A")
    action = item.raw.get("requiredAction", "N/A")
    due_date = item.raw.get("dueDate", "N/A")
    date_added = item.raw.get("dateAdded", "N/A")
    ransomware = item.raw.get("knownRansomwareCampaignUse", "Unknown")
    notes = item.raw.get("notes", "").split(";")
    cwes = ", ".join(item.raw.get("cwes", []))
    
    # Format notes as links
    notes_html = ""
    for note in notes:
        note = note.strip()
        if note:
            if note.startswith("http"):
                notes_html += f'<li><a href="{note}" target="_blank">{note}</a></li>\n'
            else:
                notes_html += f"<li>{note}</li>\n"
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .vuln-details {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #c00; margin-bottom: 20px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
        .important {{ color: #c00; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Detected and published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Added to CISA KEV: {date_added}</p>
        <p>Source: <a href="{item.link}" target="_blank">CISA Known Exploited Vulnerabilities Catalog</a></p>
    </div>
    
    <div class="content">
        <p class="important">This vulnerability has been added to the CISA Known Exploited Vulnerabilities (KEV) Catalog, 
        which means it is being actively exploited in the wild and poses a significant risk.</p>
        
        <p>{description}</p>
        
        <div class="vuln-details">
            <h2>Vulnerability Details</h2>
            <ul>
                <li><strong>CVE ID:</strong> {cve_id}</li>
                <li><strong>Vendor/Project:</strong> {vendor}</li>
                <li><strong>Product:</strong> {product}</li>
                <li><strong>Vulnerability Name:</strong> {vuln_name}</li>
                <li><strong>Date Added to KEV:</strong> {date_added}</li>
                <li><strong>Required Action:</strong> {action}</li>
                <li><strong>Due Date for Action:</strong> {due_date}</li>
                <li><strong>Known Ransomware Campaign Use:</strong> {ransomware}</li>
                <li><strong>CWE Categories:</strong> {cwes}</li>
            </ul>
            
            <h3>References</h3>
            <ul>
                {notes_html}
            </ul>
        </div>
        
        <h2>Impact</h2>
        <p>This vulnerability has been identified by CISA as being actively exploited in real-world attacks.
        Federal agencies are required to remediate this vulnerability by the due date specified in the catalog.</p>
        
        <h2>Remediation</h2>
        <p>{action}</p>
    </div>
    
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
    </div>
</body>
</html>"""


def create_usgs_article_html(item: NewsItem, timestamp_iso: str, timestamp_readable: str) -> str:
    """Create a USGS earthquake-specific article HTML."""
    # Extract properties from raw data
    properties = item.raw.get("properties", {})
    geometry = item.raw.get("geometry", {})
    
    magnitude = properties.get("mag", "N/A")
    place = properties.get("place", "N/A")
    time_ms = properties.get("time")
    time_str = datetime.fromtimestamp(time_ms / 1000, tz=datetime.now().tzinfo).strftime("%Y-%m-%d %H:%M:%S UTC") if time_ms else "N/A"
    felt = properties.get("felt", "N/A")
    alert = properties.get("alert", "none")
    tsunami = properties.get("tsunami", 0)
    
    # Get coordinates
    coords = geometry.get("coordinates", [])
    lat = coords[1] if len(coords) > 1 else "N/A"
    lon = coords[0] if len(coords) > 0 else "N/A"
    depth = coords[2] if len(coords) > 2 else "N/A"
    
    # Create alert level display
    alert_display = ""
    if alert and alert.lower() != "none":
        alert_color = {
            "green": "#a3d86c",
            "yellow": "#f3c022",
            "orange": "#e77e23",
            "red": "#e84c3d"
        }.get(alert.lower(), "#999")
        alert_display = f'<p style="background-color: {alert_color}; color: white; padding: 10px; font-weight: bold;">Alert Level: {alert.upper()}</p>'
    
    # Create tsunami warning display
    tsunami_display = ""
    if tsunami == 1:
        tsunami_display = '<p style="background-color: #c00; color: white; padding: 10px; font-weight: bold; font-size: 1.2em;">TSUNAMI WARNING ISSUED</p>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .eq-details {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #00c; margin-bottom: 20px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Detected and published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Earthquake time: {time_str}</p>
        <p>Source: <a href="{item.link}" target="_blank">USGS Earthquake Hazards Program</a></p>
    </div>
    
    {tsunami_display}
    {alert_display}
    
    <div class="content">
        <p>{item.summary}</p>
        
        <div class="eq-details">
            <h2>Earthquake Details</h2>
            <ul>
                <li><strong>Magnitude:</strong> {magnitude}</li>
                <li><strong>Location:</strong> {place}</li>
                <li><strong>Coordinates:</strong> {lat}°N, {lon}°E</li>
                <li><strong>Depth:</strong> {depth} km</li>
                <li><strong>Time:</strong> {time_str}</li>
                <li><strong>Felt Reports:</strong> {felt}</li>
            </ul>
        </div>
        
        <h2>Impact</h2>
        <p>Earthquakes of this magnitude can cause significant damage, especially in vulnerable structures.
        The actual impact depends on depth, local building codes, population density, and other factors.</p>
    </div>
    
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
        <p><small>For official information and updates, always refer to the <a href="https://earthquake.usgs.gov/" target="_blank">USGS Earthquake Hazards Program</a>.</small></p>
    </div>
</body>
</html>"""


def create_noaa_article_html(item: NewsItem, timestamp_iso: str, timestamp_readable: str) -> str:
    """Create a NOAA space weather-specific article HTML."""
    # Extract data
    issue_datetime = item.raw.get("issue_datetime", "N/A")
    product = item.raw.get("product", "N/A")
    message = item.raw.get("message", "N/A")
    alert_level = item.raw.get("alert_level", "")
    
    # Create alert level display
    alert_display = ""
    if alert_level:
        alert_display = f'<p style="background-color: #e77e23; color: white; padding: 10px; font-weight: bold;">Alert Level: {alert_level}</p>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .space-details {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #00c; margin-bottom: 20px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
        .message {{ white-space: pre-wrap; font-family: monospace; background-color: #f5f5f5; padding: 10px; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Detected and published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Alert issued: {issue_datetime}</p>
        <p>Source: <a href="{item.link}" target="_blank">NOAA Space Weather Prediction Center</a></p>
    </div>
    
    {alert_display}
    
    <div class="content">
        <div class="space-details">
            <h2>Space Weather Alert Details</h2>
            <ul>
                <li><strong>Product:</strong> {product}</li>
                <li><strong>Issued:</strong> {issue_datetime}</li>
                {f'<li><strong>Alert Level:</strong> {alert_level}</li>' if alert_level else ''}
            </ul>
            
            <h3>Message</h3>
            <div class="message">{message}</div>
        </div>
        
        <h2>Potential Impacts</h2>
        <p>Space weather events can affect satellite operations, communications, GPS, and power grids.
        The severity of these impacts depends on the strength and duration of the event.</p>
    </div>
    
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
        <p><small>For official information and updates, always refer to the <a href="https://www.swpc.noaa.gov/" target="_blank">NOAA Space Weather Prediction Center</a>.</small></p>
    </div>
</body>
</html>"""


def create_sec_article_html(item: NewsItem, timestamp_iso: str, timestamp_readable: str) -> str:
    """Create an SEC filing-specific article HTML."""
    # Extract data
    company = item.raw.get("company", "N/A")
    form_type = item.raw.get("form_type", "N/A")
    details = item.raw.get("details", "")
    event_type = item.raw.get("event_type", "N/A")
    confidence = item.raw.get("confidence", 0.0)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #333; }}
        .metadata {{ font-size: 0.9em; color: #666; margin-bottom: 20px; }}
        .content {{ margin-bottom: 30px; }}
        .sec-details {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #007; margin-bottom: 20px; }}
        .source {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <h1>{item.title}</h1>
    <div class="metadata">
        <p>Detected and published: <time datetime="{timestamp_iso}">{timestamp_readable}</time></p>
        <p>Source: <a href="{item.link}" target="_blank">SEC EDGAR Database</a></p>
    </div>
    
    <div class="content">
        <p>{item.summary}</p>
        
        <div class="sec-details">
            <h2>Filing Details</h2>
            <ul>
                <li><strong>Company:</strong> {company}</li>
                <li><strong>Form Type:</strong> {form_type}</li>
                <li><strong>Event Type:</strong> {event_type}</li>
                {f'<li><strong>Details:</strong> {details}</li>' if details else ''}
            </ul>
        </div>
        
        <h2>Significance</h2>
        <p>This filing may represent a significant corporate event that could have broader market implications.
        SEC Form {form_type} filings typically disclose {event_type.lower()} events that are material to investors.</p>
        
        <p><strong>Note:</strong> To view the complete filing, follow the link to the SEC EDGAR database.</p>
    </div>
    
    <div class="source">
        <p><a href="../">← Back to all news</a></p>
    </div>
</body>
</html>"""


def update_index_html(new_articles: List[tuple]) -> None:
    """Update the main index.html with links to new articles."""
    index_path = DOCS_DIR / "index.html"
    
    # Read the current index
    with open(index_path, "r") as f:
        content = f.read()
    
    # Find the news container div
    container_marker = '<div id="news-container">'
    container_end = '</div>'
    start_pos = content.find(container_marker) + len(container_marker)
    end_pos = content.find(container_end, start_pos)
    
    # Generate new entries
    now = datetime.now().strftime("%B %d, %Y %H:%M:%S UTC")
    now_iso = datetime.now().isoformat()
    
    entries = ""
    for item_title, item_source, article_path in new_articles:
        rel_path = os.path.relpath(article_path.parent, DOCS_DIR)
        
        # Create a badge based on source
        badge_style = ""
        if "cisa-kev" in item_source:
            badge_style = 'style="background-color: #c00; color: white; padding: 2px 5px; border-radius: 3px; font-size: 0.7em;"'
            source_display = "CISA KEV"
        elif "usgs" in item_source:
            badge_style = 'style="background-color: #00c; color: white; padding: 2px 5px; border-radius: 3px; font-size: 0.7em;"'
            source_display = "USGS"
        elif "noaa" in item_source:
            badge_style = 'style="background-color: #0c0; color: white; padding: 2px 5px; border-radius: 3px; font-size: 0.7em;"'
            source_display = "NOAA SWPC"
        elif "sec" in item_source:
            badge_style = 'style="background-color: #007; color: white; padding: 2px 5px; border-radius: 3px; font-size: 0.7em;"'
            source_display = "SEC EDGAR"
        else:
            badge_style = 'style="background-color: #777; color: white; padding: 2px 5px; border-radius: 3px; font-size: 0.7em;"'
            source_display = item_source
        
        entry = f"""
        <div class="story">
            <h2 class="story-title"><a href="{rel_path}/">{item_title}</a> <span {badge_style}>{source_display}</span></h2>
            <p class="story-meta">Published: <time datetime="{now_iso}">{now}</time></p>
            <p><a href="{rel_path}/">Read full article</a></p>
        </div>"""
        entries = entry + entries  # Prepend to show newest first
    
    # Update the content
    updated_content = content[:start_pos] + entries + content[end_pos:]
    
    # Write the updated content
    with open(index_path, "w") as f:
        f.write(updated_content)
    
    logger.info(f"Updated index.html with {len(new_articles)} new articles")


def run_monitor(monitor: Monitor) -> List[tuple]:
    """Run a monitor and generate articles for new items."""
    logger.info(f"Running monitor: {monitor.name}")
    
    try:
        # Run the monitor
        new_items = monitor.run_once()
        
        if not new_items:
            logger.info(f"No new items found for {monitor.name}")
            return []
        
        logger.info(f"Found {len(new_items)} new items for {monitor.name}")
        
        # Generate articles for each item
        articles = []
        for item in new_items:
            try:
                article_path = create_article_html(item)
                if article_path:
                    articles.append((item.title, item.source, article_path))
            except Exception as e:
                logger.error(f"Error creating article for {item.title}: {e}")
        
        return articles
    
    except Exception as e:
        logger.error(f"Error running {monitor.name} monitor: {e}")
        return []


def git_publish(message: str) -> bool:
    """Commit and push changes to GitHub."""
    try:
        subprocess.run(["git", "add", "."], cwd=project_root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=project_root, check=True)
        subprocess.run(["git", "push"], cwd=project_root, check=True)
        logger.info(f"Successfully published changes: {message}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error publishing to GitHub: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run news monitors and publish findings")
    parser.add_argument("--no-git", action="store_true", help="Skip git operations")
    parser.add_argument("--monitor", choices=["all", "cisa", "usgs", "noaa", "sec"], default="all", 
                      help="Specify which monitor(s) to run")
    args = parser.parse_args()
    
    # Initialize monitors based on arguments
    monitors = []
    
    if args.monitor in ["all", "cisa"]:
        monitors.append(CisaKevMonitor())
    if args.monitor in ["all", "usgs"]:
        monitors.append(USGSEarthquakeMonitor())
    if args.monitor in ["all", "noaa"]:
        monitors.append(NOAASWPCMonitor())
    if args.monitor in ["all", "sec"]:
        monitors.append(SECEdgarMonitor())
    
    # Run all monitors
    all_articles = []
    for monitor in monitors:
        articles = run_monitor(monitor)
        all_articles.extend(articles)
    
    # Update index and publish if we have new articles
    if all_articles:
        update_index_html(all_articles)
        
        # Commit and push changes
        if not args.no_git:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Add {len(all_articles)} new articles from {', '.join(m.name for m in monitors)} - {timestamp}"
            git_publish(message)
    else:
        logger.info("No new articles to publish")


if __name__ == "__main__":
    main()
