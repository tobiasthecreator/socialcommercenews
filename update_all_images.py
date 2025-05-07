#!/usr/bin/env python3
"""
Script to batch update all article images in the database
Uses the improved thumbnail extraction functionality to get better article images

Usage:
  python update_all_images.py [--limit=100] [--delay=0.5]

Options:
  --limit=N     Limit processing to N articles (default: process all)
  --delay=0.5   Seconds to wait between requests (default: 0.5)
"""

import sys
import time
import argparse
from main import app, db
from models import Article
from fetch_thumbnails import update_article_images_from_urls

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Update article images with enhanced extraction")
    parser.add_argument("--limit", type=int, help="Limit processing to N articles (default: all)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between requests (default: 0.5)")
    return parser.parse_args()

def update_all_article_images(limit=None, delay=0.5):
    """
    Update all article images using the improved thumbnail extraction
    
    Args:
        limit (int, optional): Limit processing to this many articles
        delay (float, optional): Seconds to wait between requests
    """
    with app.app_context():
        # Use the improved batch update function from fetch_thumbnails.py
        results = update_article_images_from_urls(db, Article)
        
        # Display summary
        print("\n===== Image Update Summary =====")
        print(f"Total articles processed: {results['total']}")
        print(f"Updated with thumbnails: {results['updated_with_thumbnail']}")
        print(f"Updated with placeholders: {results['updated_with_placeholder']}")
        print(f"Skipped: {results['skipped']}")

if __name__ == "__main__":
    args = parse_args()
    update_all_article_images(limit=args.limit, delay=args.delay)