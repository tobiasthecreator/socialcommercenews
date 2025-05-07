import os
import datetime
from datetime import timedelta
import logging
import json
import requests
import feedparser
import time
import re
import base64
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, Response
from sqlalchemy import desc, and_, func

# Import database models
from models import db, Keyword, Article, article_keyword

# Import keywords from topics.py
from topics import KEYWORDS

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "social-commerce-news-secret")

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///social_commerce_news.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_timeout": 30,
    "pool_size": 10,
    "max_overflow": 20,
    "connect_args": {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
}
db.init_app(app)

# Create all tables
with app.app_context():
    db.create_all()

def extract_actual_url_from_google_news(google_url):
    """Extract the actual article URL from a Google News URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # For standard Google News URLs
        if '/articles/' in google_url:
            # First approach: Try to extract from Google News page
            try:
                response = requests.get(google_url, headers=headers, timeout=5, allow_redirects=True)
                
                # Sometimes Google News directly redirects to the actual article
                if response.url != google_url and 'news.google.com' not in response.url:
                    logging.info(f"Google News redirected to: {response.url}")
                    return response.url
                
                # Otherwise, parse the HTML to find the link
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for redirect links
                for a_tag in soup.find_all('a'):
                    href = a_tag.get('href', '')
                    # Skip Google internal links
                    if href and isinstance(href, str) and href.startswith(('http', 'https')) and 'google.com' not in href:
                        logging.info(f"Extracted article URL from Google News: {href}")
                        return href
                    
                # If we couldn't find direct links, try looking for canonical URLs
                canonical = soup.find('link', rel='canonical')
                if canonical and canonical.get('href') and 'google.com' not in canonical.get('href'):
                    url = canonical.get('href')
                    logging.info(f"Found canonical URL: {url}")
                    return url
            except Exception as e:
                logging.error(f"Error extracting URL from Google News page: {str(e)}")
        
        # Fallback approach for RSS format URLs
        # For Google News RSS URLs, manually follow redirects to find the actual URL
        try:
            session = requests.Session()
            response = session.head(google_url, headers=headers, timeout=5, allow_redirects=True)
            final_url = response.url
            
            if final_url != google_url and 'news.google.com' not in final_url:
                logging.info(f"Followed redirect to: {final_url}")
                return final_url
        except Exception as e:
            logging.error(f"Error following Google News URL: {str(e)}")
        
        # If all extraction attempts failed, just return the original URL
        return google_url
    except Exception as e:
        logging.error(f"Error extracting actual URL from Google News: {str(e)}")
        return google_url


def fetch_news_from_google_news(keyword, max_results=25):
    """Fetch news articles for a given keyword using Google News RSS feed."""
    try:
        # Format keyword for URL
        formatted_keyword = keyword.replace(' ', '+')
        
        # Google News RSS feed URL
        rss_url = f"https://news.google.com/rss/search?q={formatted_keyword}&hl=en-US&gl=US&ceid=US:en"
        
        # Parse the RSS feed
        feed = feedparser.parse(rss_url)
        
        # Process results
        articles = []
        for entry in feed.entries[:max_results]:
            # Get the Google News URL
            google_url = entry.link
            
            # Try to unwrap the Google News URL to get the actual article URL
            actual_url = extract_actual_url_from_google_news(google_url)
            
            # If we successfully unwrapped the URL, use that; otherwise use the Google URL
            final_url = actual_url if actual_url and actual_url != google_url else google_url
            
            if actual_url and actual_url != google_url:
                logging.info(f"Unwrapped Google News URL: {google_url} -> {actual_url}")
            
            article = {
                'title': entry.title,
                'url': final_url,
                'published_date': datetime.datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.datetime.now(),
                'source': entry.source.title if hasattr(entry, 'source') and hasattr(entry.source, 'title') else "Unknown Source"
            }
            articles.append(article)
        
        logging.info(f"Fetched {len(articles)} articles for keyword '{keyword}'")
        return articles
    
    except Exception as e:
        logging.error(f"Error fetching news for keyword '{keyword}': {str(e)}")
        return []

def extract_actual_url_from_google_news(google_url):
    """Extract the actual article URL from a Google News URL."""
    from fetch_thumbnails import unwrap_google_link
    return unwrap_google_link(google_url)

def get_image_from_og_tags(url):
    """
    Try to extract an image URL from Open Graph tags or other image sources.
    Uses the improved extraction function from fetch_thumbnails.py.
    
    Args:
        url (str): The URL of the article
        
    Returns:
        str or None: The URL of the image, or None if not found
    """
    from fetch_thumbnails import get_thumbnail_from_url
    
    # Use the improved thumbnail extraction function
    image_url = get_thumbnail_from_url(url)
    return image_url if image_url else None

def generate_placeholder_image(keyword, source):
    """Generate a gradient placeholder based on source."""
    from fetch_thumbnails import get_branded_placeholder
    
    # Use our improved placeholder generator from fetch_thumbnails.py
    placeholder_data = get_branded_placeholder(source, keyword)
    return placeholder_data['image_url']


def fetch_article_content(url):
    """Fetch and extract the content from an article URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # For Google News URLs, we'll try to unwrap the URL and get the actual article
        if "news.google.com" in url:
            try:
                # Try to get the actual article URL by unwrapping the Google News URL
                actual_url = extract_actual_url_from_google_news(url)
                
                # If we successfully unwrapped the URL, use that for content fetching
                if actual_url and actual_url != url:
                    logging.info(f"Unwrapped Google News URL for content fetching: {url} -> {actual_url}")
                    # Set the URL to the actual article URL
                    url = actual_url
                else:
                    # Create a placeholder for Google News URLs we couldn't unwrap
                    title_match = re.search(r'([^\/]+)(\?|$)', url.split('articles/')[-1])
                    article_id = title_match.group(1) if title_match else "News Article"
                    
                    # Create an abbreviated placeholder without the Google News mention
                    content = "Click original source for full article content."
                    
                    # Use title as summary instead of Google News placeholder text
                    summary = article_id.replace('-', ' ')[:200]
                    
                    # Generate a placeholder image using the article ID as a seed
                    image_url = generate_placeholder_image(article_id[:30], "news.google.com")
                    
                    logging.info(f"Created placeholder for Google News article: {article_id}")
                    
                    return {
                        'content': content,
                        'summary': summary,
                        'image_url': image_url
                    }
            except Exception as e:
                logging.error(f"Error processing Google News URL: {str(e)}")
                return {
                    'content': "Click original source for full article content.",
                    'summary': article_id.replace('-', ' ')[:200],  # Use the article ID as summary
                    'image_url': generate_placeholder_image("Google News", "news.google.com")
                }
        else:
            # For regular non-Google URLs, fetch directly
            actual_url = url
            try:
                # Try to get content with a timeout
                article_response = requests.get(actual_url, headers=headers, timeout=10)
                article_response.raise_for_status()
                
                # Parse the HTML content
                soup = BeautifulSoup(article_response.text, 'html.parser')
            except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
                logging.warning(f"Request failed for {actual_url}: {str(e)}. Using placeholder.")
                return {
                    'content': f"Unable to fetch content from {actual_url}. Please visit the original article.",
                    'summary': f"Article content not available.",
                    'image_url': generate_placeholder_image("Error", "connection")
                }
        
        # Now process the content from the actual article
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Try to find an image
        image_url = None
        
        # First check for Twitter/Open Graph meta images (usually high quality)
        for meta_tag in ['og:image', 'twitter:image', 'image']:
            if image_url:
                break
                
            # Try both property and name attributes
            og_image = soup.find('meta', property=meta_tag) or soup.find('meta', attrs={'name': meta_tag})
            if og_image and og_image.get('content'):
                content = og_image.get('content')
                if content and content.startswith(('http://', 'https://')):
                    image_url = content
                    logging.info(f"Found image using meta tag {meta_tag}: {image_url}")
        
        # Next look for LD+JSON structured data which often contains high-quality images
        if not image_url:
            for script in soup.find_all('script', type='application/ld+json'):
                if script.string:
                    try:
                        json_data = json.loads(script.string)
                        # Check for image in different JSON-LD formats
                        if isinstance(json_data, dict):
                            # Handle single LD+JSON object
                            image = json_data.get('image')
                            if image:
                                if isinstance(image, str) and image.startswith(('http://', 'https://')):
                                    image_url = image
                                    logging.info(f"Found image in LD+JSON: {image_url}")
                                    break
                                elif isinstance(image, dict) and image.get('url'):
                                    img_url = image.get('url')
                                    if img_url and img_url.startswith(('http://', 'https://')):
                                        image_url = img_url
                                        logging.info(f"Found image in LD+JSON object: {image_url}")
                                        break
                                elif isinstance(image, list) and len(image) > 0:
                                    img_item = image[0]
                                    if isinstance(img_item, str) and img_item.startswith(('http://', 'https://')):
                                        image_url = img_item
                                        logging.info(f"Found image in LD+JSON array: {image_url}")
                                        break
                                    elif isinstance(img_item, dict) and img_item.get('url'):
                                        img_url = img_item.get('url')
                                        if img_url and img_url.startswith(('http://', 'https://')):
                                            image_url = img_url
                                            logging.info(f"Found image in LD+JSON array object: {image_url}")
                                            break
                    except:
                        pass  # Skip invalid JSON
        
        # If still no image, look for images with specific attributes that indicate they're the main image
        if not image_url:
            main_selectors = [
                'img[itemprop="image"]', 
                'img.main-image', 
                'img.featured-image', 
                'img.article-image',
                '.article-featured-image img', 
                '.post-thumbnail img',
                '.featured-image img',
                '.article__featured-image img'
            ]
            main_images = soup.select(', '.join(main_selectors))
            if main_images and len(main_images) > 0:
                for img in main_images:
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src:
                        # Make sure it's an absolute URL
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            # Relative URL, need to make it absolute
                            parsed_url = urlparse(actual_url)
                            base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                            src = base + src
                            
                        if src.startswith(('http://', 'https://')):
                            image_url = src
                            logging.info(f"Found image using main image selector: {image_url}")
                            break
        
        # If still no image, look for any reasonably sized image
        if not image_url:
            min_area = 40000  # Minimum area (e.g., 200x200) to qualify as article image
            largest_area = 0
            largest_image = None
            
            for img in soup.find_all('img'):
                # Skip tiny icons, spacers, and tracking pixels
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src or src.startswith('data:') or 'icon' in src.lower() or 'logo' in src.lower():
                    continue
                    
                # Get dimensions
                width = img.get('width')
                height = img.get('height')
                
                # Check for dimensions in style attribute if not in width/height attributes
                if not (width and height):
                    style = img.get('style', '')
                    width_match = re.search(r'width:\s*(\d+)px', style)
                    height_match = re.search(r'height:\s*(\d+)px', style)
                    if width_match and height_match:
                        width = width_match.group(1)
                        height = height_match.group(1)
                
                # If we have dimensions, calculate area
                if width and height and str(width).isdigit() and str(height).isdigit():
                    area = int(width) * int(height)
                    if area > largest_area:
                        largest_area = area
                        
                        # Make sure it's an absolute URL
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            # Relative URL, need to make it absolute
                            parsed_url = urlparse(actual_url)
                            base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                            src = base + src
                            
                        if src.startswith(('http://', 'https://')):
                            largest_image = src
            
            # Use the largest image if it meets our minimum size requirements
            if largest_area >= min_area and largest_image:
                image_url = largest_image
                logging.info(f"Found largest image ({largest_area} px²): {image_url}")
                
        # If we still don't have an image, try one last approach for common image patterns
        if not image_url:
            # Look for the first image that's not a logo, icon, etc.
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                    
                # Skip likely non-content images
                lower_src = src.lower()
                if any(skip in lower_src for skip in ['logo', 'icon', 'avatar', 'spinner', 'pixel', 'tracking', 'banner']):
                    continue
                
                # Make it an absolute URL if needed
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    parsed_url = urlparse(actual_url)
                    base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    src = base + src
                
                if src.startswith(('http://', 'https://')):
                    image_url = src
                    logging.info(f"Found fallback image: {image_url}")
                    break
        
        # Get text
        text = soup.get_text(separator='\n')
        
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Remove blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit content length to avoid storing too much data
        max_content_length = 10000  # Limit content to 10K characters
        if len(text) > max_content_length:
            text = text[:max_content_length] + "... [content truncated]"
        
        # Create a simple summary (first 500 characters)
        summary = text[:500] + "..." if len(text) > 500 else text
        
        return {
            'content': text,
            'summary': summary,
            'image_url': image_url
        }
    
    except Exception as e:
        logging.error(f"Error fetching article content for URL {url}: {str(e)}")
        return {
            'content': f"Error fetching content. Visit the original article at: {url}",
            'summary': f"Article summary not available. Check the original source."
        }

def store_article_in_db(article_data, keyword_ids):
    """Store article in the database and associate with keywords."""
    with app.app_context():
        try:
            # Check if article already exists (by URL)
            existing_article = Article.query.filter_by(url=article_data['url']).first()
            
            if existing_article:
                # Update existing article with keywords if needed
                for keyword_id in keyword_ids:
                    # Check if we need to add this keyword
                    if keyword_id not in [k.id for k in existing_article.keywords]:
                        keyword = db.session.get(Keyword, keyword_id)
                        if keyword:
                            existing_article.keywords.append(keyword)
                
                # If the existing article has no image or has a placeholder image
                if not existing_article.image_url or 'placehold.co' in existing_article.image_url or 'data:image/svg+xml;base64' in existing_article.image_url:
                    # First try using the image from article_data if available and not a placeholder
                    if article_data.get('image_url') and 'placehold.co' not in article_data.get('image_url', '') and 'data:image/svg+xml;base64' not in article_data.get('image_url', ''):
                        existing_article.image_url = article_data['image_url']
                        logging.info(f"Updated image for article: {existing_article.title}")
                    else:
                        # Try to fetch an image from OG tags
                        og_image = get_image_from_og_tags(existing_article.url)
                        if og_image:
                            existing_article.image_url = og_image
                            logging.info(f"Updated with OG image for article: {existing_article.title}")
                
                # Only update content if it's empty or placeholder and we have new content
                if (not existing_article.content or (existing_article.content and len(existing_article.content) < 100) or 
                    (existing_article.content and "This article is sourced from Google News" in existing_article.content)) and article_data.get('content') and len(article_data.get('content', '')) > 100:
                    existing_article.content = article_data['content']
                    existing_article.summary = article_data.get('summary', '')
                    logging.info(f"Updated content for article: {existing_article.title}")
                
                db.session.commit()
                return existing_article.id
            
            # Create new article
            new_article = Article(
                title=article_data['title'],
                url=article_data['url'],
                source=article_data['source'],
                published_date=article_data['published_date'],
                content=article_data.get('content', ''),
                summary=article_data.get('summary', '')
            )
            
            # Handle image URL - try multiple methods to get an image
            if article_data.get('image_url'):
                # Use the provided image URL if already available
                new_article.image_url = article_data['image_url']
            else:
                # Try to fetch an image from OG tags
                og_image = get_image_from_og_tags(article_data['url'])
                if og_image:
                    new_article.image_url = og_image
                    logging.info(f"Found OG image for article: {new_article.title}")
                else:
                    # Fall back to a placeholder
                    new_article.image_url = generate_placeholder_image(
                        new_article.title, 
                        new_article.source or "unknown"
                    )
                    logging.info(f"Generated placeholder image for: {new_article.title}")
            
            # Add keywords
            for keyword_id in keyword_ids:
                keyword = db.session.get(Keyword, keyword_id)
                if keyword:
                    new_article.keywords.append(keyword)
            
            db.session.add(new_article)
            db.session.commit()
            
            return new_article.id
            
        except Exception as e:
            logging.error(f"Error storing article in database: {str(e)}")
            db.session.rollback()
            return None

def collect_news_for_keywords(collect_content=True):
    """Collect news articles for all active keywords."""
    with app.app_context():
        try:
            # Get all active keywords
            active_keywords = Keyword.query.filter_by(active=True).all()
            
            if not active_keywords:
                logging.warning("No active keywords found. Run import_initial_keywords() first.")
                return []
            
            all_new_articles = []
            error_count = 0
            max_errors = 3  # Stop after encountering too many errors
            
            # Process each keyword
            for keyword in active_keywords:
                logging.info(f"Fetching news for keyword: {keyword.display_name}")
                
                # Get articles from Google News
                articles = fetch_news_from_google_news(keyword.display_name)
                logging.info(f"Found {len(articles)} articles for keyword {keyword.display_name}")
                
                # Process each article
                for article in articles:
                    try:
                        # Fetch full content if requested
                        if collect_content:
                            content_data = fetch_article_content(article['url'])
                            article.update(content_data)
                        
                        # Store in database
                        article_id = store_article_in_db(article, [keyword.id])
                        
                        if article_id:
                            all_new_articles.append({
                                'id': article_id,
                                'title': article['title'],
                                'url': article['url'],
                                'source': article['source'],
                                'keyword': keyword.display_name
                            })
                    except Exception as article_err:
                        logging.error(f"Error processing article {article.get('title', 'Unknown')}: {str(article_err)}")
                        error_count += 1
                        if error_count >= max_errors:
                            logging.warning(f"Too many errors ({error_count}), stopping article collection")
                            return all_new_articles
                
                # Be nice to the server - don't hammer it
                time.sleep(2)
            
            # Log summary
            logging.info(f"Collected {len(all_new_articles)} new articles across {len(active_keywords)} keywords")
            return all_new_articles
            
        except Exception as e:
            logging.error(f"Error in collect_news_for_keywords: {str(e)}")
            return []

# Function to import initial keywords
def import_initial_keywords():
    """Import initial keywords from topics.py if they don't exist in the database."""
    with app.app_context():
        # Check if we need to import initial keywords
        if Keyword.query.count() == 0:
            for name, display_name in KEYWORDS.items():
                # Create new keyword
                new_keyword = Keyword(
                    name=name,
                    display_name=display_name,
                    active=True
                )
                db.session.add(new_keyword)
            
            # Commit the changes
            db.session.commit()
            logging.info("Imported initial keywords from topics.py")

# Import initial keywords when starting the app
import_initial_keywords()

# Flask Routes
@app.route('/')
def index():
    """Display the dashboard homepage."""
    with app.app_context():
        # Get basic stats
        keyword_count = Keyword.query.count()
        active_keyword_count = Keyword.query.filter_by(active=True).count()
        article_count = Article.query.count()
        
        # Get recent articles
        recent_articles = Article.query.order_by(desc(Article.published_date)).limit(10).all()
        
        # Get all keywords for filtering
        keywords = Keyword.query.order_by(Keyword.display_name).all()
        
        # Get current date for footer
        now_utc = datetime.datetime.now()
        now_et = now_utc - timedelta(hours=4)  # Convert to Eastern Time
        
        return render_template('index.html', 
                              keywords=keywords,
                              keyword_count=keyword_count,
                              active_keyword_count=active_keyword_count,
                              article_count=article_count,
                              recent_articles=recent_articles,
                              now=now_utc,
                              now_et=now_et)

@app.route('/trends')
def trends_analysis():
    """Display strategic trends analysis dashboard."""
    # Get time period parameter
    time_period = request.args.get('time_period', type=int, default=30)
    
    # Calculate the date limit
    date_limit = datetime.datetime.now() - datetime.timedelta(days=time_period)
    
    # Base query for articles within time period
    base_query = Article.query.filter(Article.published_date >= date_limit)
    
    # Get article publication dates grouped by day
    publication_data = db.session.query(
        func.date(Article.published_date).label('date'),
        func.count(Article.id).label('count')
    ).filter(Article.published_date >= date_limit)\
     .group_by(func.date(Article.published_date))\
     .order_by(func.date(Article.published_date))\
     .all()
    
    # Prepare data for charts
    publication_dates = [item.date.strftime('%Y-%m-%d') for item in publication_data]
    publication_counts = [item.count for item in publication_data]
    
    # Get keyword distribution
    keyword_data = db.session.query(
        Keyword.display_name,
        func.count(article_keyword.c.article_id).label('count')
    ).join(article_keyword, Keyword.id == article_keyword.c.keyword_id)\
     .join(Article, Article.id == article_keyword.c.article_id)\
     .filter(Article.published_date >= date_limit)\
     .group_by(Keyword.display_name)\
     .order_by(desc('count'))\
     .limit(10)\
     .all()
    
    keyword_labels = [item.display_name for item in keyword_data]
    keyword_counts = [item.count for item in keyword_data]
    
    # Get source distribution
    source_data = db.session.query(
        Article.source,
        func.count(Article.id).label('count')
    ).filter(Article.published_date >= date_limit)\
     .group_by(Article.source)\
     .order_by(desc('count'))\
     .limit(10)\
     .all()
    
    source_labels = [item.source for item in source_data]
    source_counts = [item.count for item in source_data]
    
    # Get trending keywords (with growth calculation)
    # First get current period data
    current_period_data = db.session.query(
        Keyword.id,
        Keyword.display_name,
        Keyword.name,
        func.count(article_keyword.c.article_id).label('count')
    ).join(article_keyword, Keyword.id == article_keyword.c.keyword_id)\
     .join(Article, Article.id == article_keyword.c.article_id)\
     .filter(Article.published_date >= date_limit)\
     .group_by(Keyword.id, Keyword.display_name, Keyword.name)\
     .all()
    
    # Calculate previous period
    previous_date_limit = date_limit - datetime.timedelta(days=time_period)
    
    # Get previous period data
    previous_period_data = db.session.query(
        Keyword.id,
        func.count(article_keyword.c.article_id).label('count')
    ).join(article_keyword, Keyword.id == article_keyword.c.keyword_id)\
     .join(Article, Article.id == article_keyword.c.article_id)\
     .filter(Article.published_date >= previous_date_limit, Article.published_date < date_limit)\
     .group_by(Keyword.id)\
     .all()
    
    # Convert to dictionaries for easier lookup
    current_counts = {item.id: {'keyword': item.display_name, 'name': item.name, 'count': item.count} for item in current_period_data}
    previous_counts = {item.id: item.count for item in previous_period_data}
    
    # Calculate percentage change
    trending_keywords = []
    for keyword_id, data in current_counts.items():
        previous_count = previous_counts.get(keyword_id, 0)
        if previous_count == 0:
            # If no previous data, set change to 100% (new keyword)
            change = 100
        else:
            change = round(((data['count'] - previous_count) / previous_count) * 100)
        
        # Get the latest articles for this keyword
        latest_articles = db.session.query(Article)\
            .join(article_keyword, Article.id == article_keyword.c.article_id)\
            .filter(article_keyword.c.keyword_id == keyword_id)\
            .filter(Article.published_date >= date_limit)\
            .order_by(desc(Article.published_date))\
            .limit(5)\
            .all()
        
        # Format the articles
        latest_articles_formatted = []
        for article in latest_articles:
            latest_articles_formatted.append({
                'id': article.id,
                'title': article.title,
                'date': article.published_date.strftime('%Y-%m-%d') if article.published_date else 'Unknown',
                'source': article.source
            })
        
        trending_keywords.append({
            'keyword': data['keyword'],
            'name': data['name'],
            'count': data['count'],
            'change': change,
            'articles': latest_articles_formatted
        })
    
    # Sort by change percentage (descending)
    trending_keywords.sort(key=lambda x: x['change'], reverse=True)
    trending_keywords = trending_keywords[:6]  # Top 6 trending keywords
    
    # Get hot topics (most engaged articles)
    hot_topics_query = Article.query.filter(Article.published_date >= date_limit)
    
    # Get most recent important articles
    hot_topics = hot_topics_query.order_by(desc(Article.published_date)).limit(6).all()
    
    # Format for the template
    hot_topics_formatted = []
    for article in hot_topics:
        hot_topics_formatted.append({
            'id': article.id,
            'title': article.title,
            'summary': article.summary[:150] + "..." if article.summary and len(article.summary) > 150 else article.summary,
            'url': article.url,
            'date': article.published_date.strftime('%Y-%m-%d') if article.published_date else 'Unknown',
            'keywords': [k.display_name for k in article.keywords],
            'source': article.source
        })
    
    # NEW: Day of Week Analysis - when are most articles published?
    weekday_data = db.session.query(
        func.extract('dow', Article.published_date).label('weekday'),
        func.count(Article.id).label('count')
    ).filter(Article.published_date >= date_limit)\
     .group_by('weekday')\
     .order_by('weekday')\
     .all()
    
    weekday_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    weekday_counts = [0] * 7  # Initialize with zeros
    
    for item in weekday_data:
        weekday_index = int(item.weekday)
        weekday_counts[weekday_index] = item.count
    
    # Content length analysis by source has been removed
    # Define empty variables to avoid undefined variable errors
    content_length_labels = []
    content_length_values = []
    
    # NEW: Related topics analysis - find keywords that appear together
    # This requires a more complex query to find co-occurring keywords
    related_topics = []
    
    # Get all active keywords
    active_keywords = Keyword.query.filter_by(active=True).all()
    
    # Create a matrix of keyword relationships
    keyword_matrix = {}
    
    # For each article, record which keywords appear together
    recent_articles = Article.query.filter(Article.published_date >= date_limit).all()
    
    for article in recent_articles:
        # Get all keyword IDs for this article
        keyword_ids = [k.id for k in article.keywords]
        # For each pair of keywords, increment their co-occurrence count
        for i, kid1 in enumerate(keyword_ids):
            if kid1 not in keyword_matrix:
                keyword_matrix[kid1] = {}
            for kid2 in keyword_ids[i+1:]:
                if kid2 not in keyword_matrix[kid1]:
                    keyword_matrix[kid1][kid2] = 0
                keyword_matrix[kid1][kid2] += 1
                
                # Also update the reverse relationship
                if kid2 not in keyword_matrix:
                    keyword_matrix[kid2] = {}
                if kid1 not in keyword_matrix[kid2]:
                    keyword_matrix[kid2][kid1] = 0
                keyword_matrix[kid2][kid1] += 1
    
    # Find the strongest relationships
    strongest_relationships = []
    keyword_dict = {k.id: k.display_name for k in active_keywords}
    
    for kid1, relations in keyword_matrix.items():
        for kid2, count in relations.items():
            if kid1 in keyword_dict and kid2 in keyword_dict:
                strongest_relationships.append({
                    'keyword1': keyword_dict[kid1],
                    'keyword2': keyword_dict[kid2],
                    'count': count
                })
    
    # Sort by count (descending) and take top 10
    strongest_relationships.sort(key=lambda x: x['count'], reverse=True)
    related_topics = strongest_relationships[:10]
    
    # NEW: Geographic focus - extract location information from article titles
    # This is a simplified approach - in a real system you might use NLP
    common_locations = [
        'US', 'USA', 'United States', 'China', 'UK', 'India', 
        'Europe', 'Asia', 'Africa', 'Australia', 'Canada', 'Japan',
        'Brazil', 'Russia', 'Germany', 'France', 'Italy', 'Spain'
    ]
    
    location_counts = {}
    for location in common_locations:
        count = Article.query.filter(
            Article.published_date >= date_limit,
            Article.title.ilike(f'%{location}%')
        ).count()
        if count > 0:
            location_counts[location] = count
    
    # Sort by count (descending) and take top 8
    sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    geo_labels = [item[0] for item in sorted_locations]
    geo_counts = [item[1] for item in sorted_locations]
    
    # NEW: Weekly article volume trend analysis
    if time_period >= 28:  # Only show for periods of at least 4 weeks
        # Group by week
        weekly_data = []
        current_date = date_limit
        while current_date <= datetime.datetime.now():
            week_end = current_date + datetime.timedelta(days=7)
            count = Article.query.filter(
                Article.published_date >= current_date,
                Article.published_date < week_end
            ).count()
            weekly_data.append({
                'week': current_date.strftime('%Y-%m-%d'),
                'count': count
            })
            current_date = week_end
        
        weekly_labels = [item['week'] for item in weekly_data]
        weekly_counts = [item['count'] for item in weekly_data]
    else:
        weekly_labels = []
        weekly_counts = []
    
    # Competitor Analysis has been removed
    competitor_data = []
    competitor_groups = {}
    
    # Get current date for footer
    now = datetime.datetime.now()
    
    return render_template('trends.html',
                          time_period=time_period,
                          publication_dates=publication_dates,
                          publication_counts=publication_counts,
                          keyword_labels=keyword_labels,
                          keyword_counts=keyword_counts,
                          source_labels=source_labels,
                          source_counts=source_counts,
                          trending_keywords=trending_keywords,
                          weekday_names=weekday_names,
                          weekday_counts=weekday_counts,
                          related_topics=related_topics,
                          geo_labels=geo_labels,
                          geo_counts=geo_counts,
                          weekly_labels=weekly_labels,
                          weekly_counts=weekly_counts,
                          competitor_data=competitor_data,
                          competitor_groups=competitor_groups,
                          now=now,
                          now_et=now - timedelta(hours=4),
                          article_count=Article.query.count())

@app.route('/keywords')
def manage_keywords():
    """Display the keyword management page."""
    keywords = Keyword.query.order_by(Keyword.name).all()
    
    # Get current date for footer
    now_utc = datetime.datetime.now()
    now_et = now_utc - timedelta(hours=4)  # Convert to Eastern Time
    
    return render_template('keywords.html', keywords=keywords, now=now_utc, now_et=now_et)

@app.route('/keywords/add', methods=['POST'])
def add_keyword():
    """Add a new keyword to track."""
    try:
        name = request.form.get('name')
        display_name = request.form.get('display_name')
        
        # Validate required fields
        if not name or not display_name:
            flash('All fields are required', 'danger')
            return redirect(url_for('manage_keywords'))
        
        # Check if keyword already exists
        existing_keyword = Keyword.query.filter_by(name=name).first()
        if existing_keyword:
            flash(f'Keyword with name "{name}" already exists', 'warning')
            return redirect(url_for('manage_keywords'))
        
        # Create new keyword
        new_keyword = Keyword(
            name=name,
            display_name=display_name,
            active=True
        )
        db.session.add(new_keyword)
        db.session.commit()
        
        flash(f'Keyword "{display_name}" added successfully', 'success')
    except Exception as e:
        logging.error(f"Error adding keyword: {str(e)}")
        flash(f'Error adding keyword: {str(e)}', 'danger')
    
    return redirect(url_for('manage_keywords'))

@app.route('/keywords/<int:keyword_id>/edit', methods=['POST'])
def edit_keyword(keyword_id):
    """Edit an existing keyword."""
    try:
        keyword = Keyword.query.get_or_404(keyword_id)
        
        # Update fields
        keyword.name = request.form.get('name')
        keyword.display_name = request.form.get('display_name')
        keyword.updated_at = datetime.datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Keyword "{keyword.display_name}" updated successfully', 'success')
    except Exception as e:
        logging.error(f"Error editing keyword: {str(e)}")
        flash(f'Error editing keyword: {str(e)}', 'danger')
    
    return redirect(url_for('manage_keywords'))

@app.route('/keywords/<int:keyword_id>/toggle', methods=['POST'])
def toggle_keyword(keyword_id):
    """Toggle a keyword's active status."""
    try:
        keyword = Keyword.query.get_or_404(keyword_id)
        keyword.active = not keyword.active
        db.session.commit()
        
        status = 'activated' if keyword.active else 'deactivated'
        flash(f'Keyword "{keyword.display_name}" {status} successfully', 'success')
    except Exception as e:
        logging.error(f"Error toggling keyword: {str(e)}")
        flash(f'Error toggling keyword: {str(e)}', 'danger')
    
    return redirect(url_for('manage_keywords'))

@app.route('/keywords/<int:keyword_id>/delete', methods=['POST'])
def delete_keyword(keyword_id):
    """Delete a keyword."""
    try:
        keyword = Keyword.query.get_or_404(keyword_id)
        display_name = keyword.display_name
        
        db.session.delete(keyword)
        db.session.commit()
        
        flash(f'Keyword "{display_name}" deleted successfully', 'success')
    except Exception as e:
        logging.error(f"Error deleting keyword: {str(e)}")
        flash(f'Error deleting keyword: {str(e)}', 'danger')
    
    return redirect(url_for('manage_keywords'))

@app.route('/articles')
def articles_list():
    """Display a list of all articles."""
    # Get filter parameters
    keyword_id = request.args.get('keyword_id', type=int)
    days = request.args.get('days', type=int, default=7)
    
    # Base query
    query = Article.query
    
    # Apply filters
    if keyword_id:
        # Filter by keyword
        keyword = Keyword.query.get(keyword_id)
        if keyword:
            query = query.join(Article.keywords).filter(Keyword.id == keyword_id)
    
    if days:
        # Filter by date
        date_limit = datetime.datetime.now() - datetime.timedelta(days=days)
        query = query.filter(Article.published_date >= date_limit)
    
    # Get the articles
    articles = query.order_by(desc(Article.published_date)).all()
    
    # Get all keywords for the filter dropdown
    keywords = Keyword.query.order_by(Keyword.display_name).all()
    
    # Get current date for footer
    now_utc = datetime.datetime.now()
    now_et = now_utc - timedelta(hours=4)  # Convert to Eastern Time
    
    return render_template('articles.html', 
                          articles=articles, 
                          keywords=keywords,
                          active_keyword_id=keyword_id,
                          active_days=days,
                          now=now_utc,
                          now_et=now_et,
                          article_count=Article.query.count())

@app.route('/articles/<int:article_id>')
def article_detail(article_id):
    """Display details for a specific article."""
    article = Article.query.get_or_404(article_id)
    
    # Get current date for footer
    now_utc = datetime.datetime.now()
    now_et = now_utc - timedelta(hours=4)  # Convert to Eastern Time
    
    return render_template('article_detail.html', article=article, now=now_utc, now_et=now_et)

@app.route('/articles/export')
def export_articles():
    """Export articles as CSV."""
    # Get filter parameters
    keyword_id = request.args.get('keyword_id', type=int)
    days = request.args.get('days', type=int, default=7)
    
    # Base query
    query = Article.query
    
    # Apply filters
    if keyword_id:
        # Filter by keyword
        keyword = Keyword.query.get(keyword_id)
        if keyword:
            query = query.join(Article.keywords).filter(Keyword.id == keyword_id)
    
    if days:
        # Filter by date
        date_limit = datetime.datetime.now() - datetime.timedelta(days=days)
        query = query.filter(Article.published_date >= date_limit)
    
    # Get the articles
    articles = query.order_by(desc(Article.published_date)).all()
    
    # Create CSV data
    csv_data = "Title,Source,Published Date,URL,Summary\n"
    for article in articles:
        # Format the date
        date_str = article.published_date.strftime('%Y-%m-%d') if article.published_date else ''
        
        # Escape quotes in the title and summary
        title = article.title.replace('"', '""')
        summary = article.summary.replace('"', '""') if article.summary else ''
        
        # Add to CSV
        csv_data += f'"{title}","{article.source}","{date_str}","{article.url}","{summary}"\n'
    
    # Return as a downloadable file
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=social_commerce_articles.csv"}
    )

@app.route('/export-for-chatgpt')
def export_for_chatgpt():
    """Export articles in a format suitable for ChatGPT."""
    # Get filter parameters
    keyword_id = request.args.get('keyword_id', type=int)
    days = request.args.get('days', type=int, default=7)
    
    # Base query
    query = Article.query
    
    # Apply filters
    if keyword_id:
        # Filter by keyword
        keyword = Keyword.query.get(keyword_id)
        if keyword:
            query = query.join(Article.keywords).filter(Keyword.id == keyword_id)
            keyword_name = keyword.display_name
        else:
            keyword_name = "All Keywords"
    else:
        keyword_name = "All Keywords"
    
    if days:
        # Filter by date
        date_limit = datetime.datetime.now() - datetime.timedelta(days=days)
        query = query.filter(Article.published_date >= date_limit)
        date_range = f"Last {days} days"
    else:
        date_range = "All time"
    
    # Get the articles
    articles = query.order_by(desc(Article.published_date)).all()
    
    # Create JSON data for ChatGPT
    articles_data = []
    for article in articles:
        # Format the date
        date_str = article.published_date.strftime('%Y-%m-%d') if article.published_date else 'Unknown'
        
        keywords = [k.display_name for k in article.keywords]
        
        # Add article data
        articles_data.append({
            "title": article.title,
            "source": article.source,
            "date": date_str,
            "url": article.url,
            "summary": article.summary,
            "keywords": keywords
        })
    
    chatgpt_data = {
        "filter": {
            "keyword": keyword_name,
            "date_range": date_range
        },
        "articles": articles_data,
        "instruction": "Please create a newsletter section summarizing these articles about " + keyword_name
    }
    
    # Convert to JSON string with nice formatting
    json_data = json.dumps(chatgpt_data, indent=2)
    
    # Return as a downloadable file
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename=newsletter_data_{keyword_name.lower().replace(' ', '_')}.json"}
    )

@app.route('/update', methods=['GET'])
def update_data():
    """Display when articles were last updated."""
    # Instead of triggering collection, just show when the last article was collected
    try:
        last_article = Article.query.order_by(desc(Article.collected_at)).first()
        if last_article:
            flash(f'Articles last updated on {last_article.collected_at.strftime("%B %d, %Y at %H:%M")}', 'info')
        else:
            flash('No articles have been collected yet', 'info')
        
        return redirect(url_for('articles_list'))
    except Exception as e:
        logging.error(f"Error checking update status: {str(e)}")
        flash(f'Error checking update status: {str(e)}', 'danger')
        return redirect(url_for('index'))

def main():
    """Main function to run the social commerce news collection."""
    try:
        # Check if we need to import keywords
        with app.app_context():
            if Keyword.query.count() == 0:
                import_initial_keywords()
                
        # Collect news articles
        collect_news_for_keywords()
    except Exception as e:
        logging.error(f"An error occurred in main: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if os.environ.get('FLASK_ENV') == 'development':
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        # Run data collection if executed as a script
        main()