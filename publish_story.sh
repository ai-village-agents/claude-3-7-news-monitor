#!/bin/bash

# Simple script to quickly publish breaking news articles

# Check for required arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 \"Title\" \"Summary\" \"Source URL\""
    exit 1
fi

TITLE="$1"
SUMMARY="$2"
SOURCE_URL="$3"

# Run the article generator
python3 ~/claude-3-7-news-monitor/src/generate_article_fixed.py "$TITLE" "$SUMMARY" "$SOURCE_URL"

# Get the slug from the title for use in git commit
SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9 -' | tr ' ' '-')

# Commit and push to GitHub
cd ~/claude-3-7-news-monitor/
git add .
git commit -m "Add breaking news: $TITLE"
git push

echo "Article published and pushed to GitHub: $TITLE"
