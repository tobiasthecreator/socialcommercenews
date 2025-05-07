import requests
from bs4 import BeautifulSoup
import logging
import time
import re
import json
from urllib.parse import urlparse, parse_qs, unquote
from functools import lru_cache
from cachetools import TTLCache
import base64

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Use a TTL cache for thumbnail URLs - will expire after 7 days (604800 seconds)
# maxsize is the maximum number of items to cache
thumbnail_cache = TTLCache(maxsize=1000, ttl=604800)
domains_cache = TTLCache(maxsize=1000, ttl=604800)

# Marker for Google placeholder images
GOOGLE_PLACEHOLDER_SUBSTR = 'news.google.com/img/icons/'

def unwrap_google_link(url):
    """
    Extracts the actual article URL from a Google News URL
    
    Args:
        url (str): Possibly a Google News URL that needs unwrapping
        
    Returns:
        str: The unwrapped URL, or the original if not a Google URL
    """
    try:
        # Case 1: https://www.google.com/url?....&url=REAL&...
        if 'google.com/url' in url:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            if 'url' in query_params:
                actual_url = query_params['url'][0]
                return unquote(actual_url)
                
        # Case 2: news.google.com/rss/articles/...
        if 'news.google.com' in url:
            # Google adds the real link after "url=" inside the string
            match = re.search(r'url=(https?:\/\/[^&]+)', url)
            if match:
                return unquote(match.group(1))
                
        # Case 3: AMP URLs
        if '/amp/' in url:
            # Extract the canonical URL if possible
            parsed = urlparse(url)
            path_parts = parsed.path.split('/amp/')
            if len(path_parts) > 1:
                canonical_path = path_parts[1]
                return f"{parsed.scheme}://{parsed.netloc}/{canonical_path}"
    
    except Exception as e:
        logging.warning(f"Error unwrapping URL {url}: {str(e)}")
    
    return url  # Return original if we can't unwrap it

def looks_like_google_placeholder(image_url):
    """
    Check if an image URL appears to be a Google placeholder image
    
    Args:
        image_url (str): The image URL to check
        
    Returns:
        bool: True if it looks like a Google placeholder, False otherwise
    """
    if not image_url:
        return True
    
    if GOOGLE_PLACEHOLDER_SUBSTR in image_url:
        return True
        
    # Additional checks for Google placeholders could be added here
    return False

def get_domain_from_url(url):
    """
    Extract the domain name from a URL
    
    Args:
        url (str): The URL to extract the domain from
        
    Returns:
        str: The domain name
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Remove www. if present
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain
    except:
        # If parsing fails, return a default
        return "unknown"

def get_favicon_url(domain):
    """
    Get a favicon URL for a domain using Clearbit's logo API
    
    Args:
        domain (str): The domain to get a favicon for
        
    Returns:
        str: The favicon URL
    """
    return f"https://logo.clearbit.com/{domain}"

def fetch_microlink_preview(url):
    """
    Simulate Microlink API by using a more advanced extraction approach
    
    This function attempts to extract images using various advanced methods
    when simple meta tag extraction fails. It's a fallback similar to how the
    Microlink API would work.
    
    Args:
        url (str): The URL to extract an image from
        
    Returns:
        str: The image URL, or empty string if none found
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Fetch with a more generous timeout for complex pages
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code != 200:
            return ""
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to extract from JSON-LD structured data first (often has high quality images)
        for script in soup.find_all('script', type='application/ld+json'):
            if script.string:
                try:
                    data = json.loads(script.string)
                    # Handle different JSON-LD formats
                    if isinstance(data, dict):
                        # Single item
                        img = data.get('image')
                        if img:
                            if isinstance(img, str):
                                return img
                            elif isinstance(img, dict) and 'url' in img:
                                return img['url']
                            elif isinstance(img, list) and len(img) > 0:
                                first_img = img[0]
                                if isinstance(first_img, str):
                                    return first_img
                                elif isinstance(first_img, dict) and 'url' in first_img:
                                    return first_img['url']
                    elif isinstance(data, list) and len(data) > 0:
                        # Array of items
                        for item in data:
                            if isinstance(item, dict) and 'image' in item:
                                img = item['image']
                                if isinstance(img, str):
                                    return img
                                elif isinstance(img, dict) and 'url' in img:
                                    return img['url']
                except:
                    # Skip invalid JSON
                    pass
        
        # Look for schema.org image property
        schema_img = soup.find('[itemprop="image"]')
        if schema_img:
            src = schema_img.get('src') or schema_img.get('content')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                return src
        
        # Try picture elements with source tags (responsive images)
        pictures = soup.find_all('picture')
        for picture in pictures:
            # Look for the highest quality source
            sources = picture.find_all('source')
            for source in sources:
                src = source.get('srcset')
                if src:
                    # Extract the first image from srcset
                    srcset_parts = src.split(',')
                    if srcset_parts:
                        first_img = srcset_parts[0].strip().split(' ')[0]
                        if first_img.startswith('//'):
                            first_img = 'https:' + first_img
                        if first_img.startswith('http'):
                            return first_img
            
            # Fallback to img tag inside picture
            img = picture.find('img')
            if img:
                src = img.get('src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    if src.startswith('http'):
                        return src
        
        # Look for any large images with priority to ones in articles
        min_area = 40000  # Minimum area (e.g., 200x200) to qualify as article image
        largest_area = 0
        largest_img = None
        
        priority_containers = soup.select('article, .article, .post, main, .content, .main')
        containers = [soup] + priority_containers  # Search entire document, but prioritize content areas
        
        for container in containers:
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src or src.startswith('data:'):
                    continue
                
                # Filter out likely non-content images
                lower_src = src.lower()
                if any(skip in lower_src for skip in ['logo', 'icon', 'avatar', 'spinner', 'pixel', 'tracking', 'banner', 'advertisement', 'ad-']):
                    continue
                
                # Get dimensions
                width = img.get('width')
                height = img.get('height')
                
                # Check for dimensions in style attribute
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
                        
                        # Make it an absolute URL if needed
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            parsed_url = urlparse(url)
                            base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                            src = base + src
                            
                        if src.startswith(('http://', 'https://')):
                            largest_img = src
                
                # If we found an image with sufficient size in a priority container, use it
                if largest_area >= min_area and container != soup:
                    return largest_img
        
        # Return the largest image found in any container if it meets the size requirement
        if largest_area >= min_area and largest_img:
            return largest_img
            
        return ""
    except Exception as e:
        logging.warning(f"Error in advanced image extraction: {str(e)}")
        return ""

def get_thumbnail_from_url(raw_url):
    """
    Extract thumbnail URL from Open Graph (og:image) or Twitter card (twitter:image) meta tags
    Uses TTL cache to avoid re-fetching the same URL repeatedly
    
    Args:
        raw_url (str): The URL of the article to fetch the thumbnail from
        
    Returns:
        str: The URL of the thumbnail image, or empty string if not found
    """
    # Check cache first
    if raw_url in thumbnail_cache:
        return thumbnail_cache[raw_url]
        
    # Unwrap Google News and other wrapped URLs first
    article_url = unwrap_google_link(raw_url)
    
    try:
        # Add timeout to avoid hanging on slow responses
        response = requests.get(article_url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        if response.status_code != 200:
            logging.warning(f"Failed to fetch {article_url} - Status code: {response.status_code}")
            thumbnail_cache[raw_url] = ""
            return ""
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find Open Graph image
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            img_url = og_image['content']
            # Verify it's not a Google placeholder
            if not looks_like_google_placeholder(img_url):
                thumbnail_cache[raw_url] = img_url
                return img_url
        
        # Try to find Twitter image as fallback
        twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image and twitter_image.get('content'):
            img_url = twitter_image['content']
            if not looks_like_google_placeholder(img_url):
                thumbnail_cache[raw_url] = img_url
                return img_url
        
        # Try to find any large image in the article
        # Look for article image, large image, or hero image
        img_selectors = [
            '.article-image img', 
            '.featured-image img', 
            '.hero-image img', 
            'article img.wp-post-image',
            'img.attachment-large',
            'img.size-large'
        ]
        
        for selector in img_selectors:
            images = soup.select(selector)
            if images and len(images) > 0:
                for img in images:
                    src = img.get('src') or img.get('data-src')
                    if src and (src.startswith('http') or src.startswith('//')):
                        if src.startswith('//'):
                            src = 'https:' + src
                        if not looks_like_google_placeholder(src):
                            thumbnail_cache[raw_url] = src
                            return src
        
        # If we got here, we haven't found a suitable image with basic methods
        # Fall back to more advanced extraction (similar to microlink API)
        logging.info(f"Using advanced image extraction for {article_url}")
        advanced_img = fetch_microlink_preview(article_url)
        if advanced_img and not looks_like_google_placeholder(advanced_img):
            thumbnail_cache[raw_url] = advanced_img
            return advanced_img
            
        # No image found - cache empty string to avoid repeated attempts
        thumbnail_cache[raw_url] = ""
        return ""
        
    except Exception as e:
        logging.warning(f"Error fetching thumbnail from {article_url}: {str(e)}")
        thumbnail_cache[raw_url] = ""
        return ""

def get_branded_placeholder(article_url, title=None):
    """
    Generate a branded placeholder for articles without images
    Uses either a gradient or a solid color background with site favicon
    
    Args:
        article_url (str): The article URL to use for domain extraction
        title (str, optional): The article title for additional context
    
    Returns:
        dict: Dictionary with image_url, favicon_url, and domain
    """
    domain = get_domain_from_url(article_url)
    
    # Choose color based on domain
    # We could expand this to use gradients as specified in your JS code
    color_map = {
        'a': '#FF5A3C', 'b': '#0EA5E9', 'c': '#34D399', 'd': '#EC4899',
        'e': '#8B5CF6', 'f': '#FBBF24', 'g': '#6366F1', 'h': '#059669',
        'i': '#3B82F6', 'j': '#EF4444', 'k': '#14B8A6', 'l': '#F97316',
        'm': '#84CC16', 'n': '#A855F7', 'o': '#F43F5E', 'p': '#10B981',
        'q': '#F59E0B', 'r': '#6EE7B7', 's': '#9333EA', 't': '#22D3EE',
        'u': '#F97316', 'v': '#FCD34D', 'w': '#4F46E5', 'x': '#0284C7',
        'y': '#7C3AED', 'z': '#C026D3', '0': '#78716C', '1': '#8B5CF6',
        '2': '#EC4899', '3': '#4ADE80', '4': '#FB923C', '5': '#4F46E5',
        '6': '#06B6D4', '7': '#0EA5E9', '8': '#0284C7', '9': '#2563EB'
    }
    
    # Get the first character of the domain in lowercase
    first_char = domain.lower()[0] if domain and len(domain) > 0 else 'n'
    
    # Get the color from the map, or use a default color if not found
    primary_color = color_map.get(first_char, '#3d4b66')
    
    # For simplicity, use one of four gradient patterns
    gradients = [
        f"from-[{primary_color}]/90 to-[#FBBF24]/80",  # warm gradient
        f"from-[{primary_color}]/90 to-[#6366F1]/80",  # cool gradient
        f"from-[{primary_color}]/90 to-[#059669]/80",  # green gradient
        f"from-[{primary_color}]/90 to-[#8B5CF6]/80"   # purple gradient
    ]
    
    # Choose gradient based on domain hash
    gradient_idx = hash(domain) % len(gradients)
    gradient = gradients[gradient_idx]
    
    # Convert to an SVG data URL
    from_color = primary_color
    to_color = gradient.split('to-[')[1].split(']/')[0]
    
    # Create SVG with linear gradient
    svg_content = f'''
    <svg xmlns="http://www.w3.org/2000/svg" width="800" height="400">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:{from_color};stop-opacity:0.9" />
                <stop offset="100%" style="stop-color:{to_color};stop-opacity:0.8" />
            </linearGradient>
        </defs>
        <rect width="800" height="400" fill="url(#grad)" />
    </svg>
    '''
    
    svg_bytes = svg_content.strip().encode('utf-8')
    b64_svg = base64.b64encode(svg_bytes).decode('utf-8')
    image_url = f"data:image/svg+xml;base64,{b64_svg}"
    
    # Get the favicon URL for the domain
    favicon_url = get_favicon_url(domain)
    
    return {
        'image_url': image_url,
        'favicon_url': favicon_url,
        'domain': domain
    }

def update_article_images_from_urls(db, Article):
    """
    Updates all articles in the database with images extracted from their URLs
    Uses improved image extraction with fallbacks and branded placeholders
    
    Args:
        db: SQLAlchemy database connection
        Article: Article model class
        
    Returns:
        dict: Statistics about the update process
    """
    # Get all articles that might need image updates
    articles_needing_images = Article.query.filter(
        (Article.image_url.is_(None)) | 
        (Article.image_url == "") | 
        (Article.image_url.like('%placeholder%')) |
        (Article.image_url.like('%data:image/svg%'))
    ).all()
    
    # Also update Google News URLs that might have placeholder images
    google_articles = Article.query.filter(
        Article.url.like('%news.google.com%')
    ).all()
    
    # Combine the lists, removing duplicates
    article_ids = set()
    articles = []
    
    for article in articles_needing_images + google_articles:
        if article.id not in article_ids:
            articles.append(article)
            article_ids.add(article.id)
    
    total_count = len(articles)
    updated_with_thumbnail = 0
    updated_with_placeholder = 0
    skipped = 0
    
    logging.info(f"Starting batch image update for {total_count} articles")
    
    for i, article in enumerate(articles):
        # Log progress periodically
        if i % 10 == 0 and i > 0:
            logging.info(f"Progress: {i}/{total_count} articles processed")
            logging.info(f"Stats: {updated_with_thumbnail} w/thumbnails, {updated_with_placeholder} w/placeholders, {skipped} skipped")
            # Commit changes in batches to avoid large transactions
            db.session.commit()
        
        try:
            # Check if this is a Google News URL that needs unwrapping
            original_url = article.url
            if "news.google.com" in original_url:
                unwrapped_url = unwrap_google_link(original_url)
                if unwrapped_url and unwrapped_url != original_url:
                    logging.info(f"Unwrapped Google URL: {original_url[:50]}... -> {unwrapped_url[:50]}...")
                    # Update the article URL to the unwrapped version
                    article.url = unwrapped_url
            
            # Try to get a real thumbnail
            thumbnail_url = get_thumbnail_from_url(article.url)
            
            if thumbnail_url:
                # We successfully found a thumbnail!
                old_image = article.image_url or "No image"
                article.image_url = thumbnail_url
                updated_with_thumbnail += 1
                logging.info(f"Updated image for article [{article.id}]: {article.title[:50]}...")
            else:
                # No thumbnail found, use a branded placeholder
                # Only update if current image is empty or a basic placeholder
                if not article.image_url or 'placeholder' in article.image_url or 'data:image/svg' in article.image_url:
                    placeholder_data = get_branded_placeholder(article.url, article.title)
                    article.image_url = placeholder_data['image_url']
                    # If we want to store domain and favicon data, we'd need to add those fields to the Article model
                    updated_with_placeholder += 1
                    logging.info(f"Created branded placeholder for article [{article.id}]: {article.title[:50]}...")
                else:
                    # Article already has a non-placeholder image
                    skipped += 1
            
            # Be nice to servers - don't hammer them
            time.sleep(0.5)
            
        except Exception as e:
            logging.error(f"Error updating image for article {article.id}: {str(e)}")
            skipped += 1
            # Continue with the next article
            continue
    
    # Final commit for any remaining changes
    db.session.commit()
    
    # Final summary
    logging.info(f"Image update complete: {total_count} articles processed")
    logging.info(f"Successfully updated with thumbnails: {updated_with_thumbnail}")
    logging.info(f"Updated with branded placeholders: {updated_with_placeholder}")
    logging.info(f"Skipped: {skipped}")
    
    return {
        'total': total_count,
        'updated_with_thumbnail': updated_with_thumbnail,
        'updated_with_placeholder': updated_with_placeholder,
        'skipped': skipped
    }

if __name__ == "__main__":
    # This allows running the script directly to update all article images
    from main import db, app
    from models import Article
    
    with app.app_context():
        update_article_images_from_urls(db, Article)