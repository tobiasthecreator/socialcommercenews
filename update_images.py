import logging
import time
from flask import Flask
from main import app, db, Article, get_image_from_og_tags, generate_placeholder_image, extract_actual_url_from_google_news
from fetch_thumbnails import get_thumbnail_from_url, unwrap_google_link

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_placeholder_svg(title, source="unknown"):
    """
    Generate a simple colored SVG placeholder for articles
    
    Args:
        title (str): The article title to use in the placeholder
        source (str): The source name to use for color determination
    
    Returns:
        str: URL for the placeholder SVG
    """
    # Use the generate_placeholder_image function from main.py
    return generate_placeholder_image(title, source)

def update_article_images():
    """
    Update all article images by attempting to extract Open Graph images
    from their source URLs
    """
    with app.app_context():
        # Get all articles that have no image or have a placeholder image
        articles = Article.query.filter(
            (Article.image_url.is_(None)) | 
            (Article.image_url == "") | 
            (Article.image_url.like('%data:image/svg+xml;base64%'))
        ).all()
        
        total_count = len(articles)
        updated_count = 0
        failed_count = 0
        
        logging.info(f"Found {total_count} articles that need image updates")
        
        for i, article in enumerate(articles):
            # Log progress every 10 articles
            if i % 10 == 0 and i > 0:
                logging.info(f"Progress: {i}/{total_count} articles processed, {updated_count} updated, {failed_count} failed")
            
            try:
                # Try to extract an image from the article's URL
                image_url = get_image_from_og_tags(article.url)
                
                if image_url:
                    # We found a valid image URL from OG tags
                    article.image_url = image_url
                    db.session.commit()
                    updated_count += 1
                    logging.info(f"Updated image for article: {article.title[:30]}...")
                else:
                    # If we couldn't find an OG image, ensure we have at least a placeholder
                    if not article.image_url:
                        article.image_url = create_placeholder_svg(article.title, article.source)
                        db.session.commit()
                        logging.info(f"Created placeholder for article: {article.title[:30]}...")
                    failed_count += 1
                
                # Be nice to servers - don't hammer them
                time.sleep(0.5)
                
            except Exception as e:
                logging.error(f"Error updating image for article {article.id}: {str(e)}")
                failed_count += 1
                # Continue with the next article
                continue
        
        # Final summary
        logging.info(f"Image update complete: {total_count} articles processed")
        logging.info(f"Successfully updated: {updated_count}")
        logging.info(f"Failed to update: {failed_count}")
        
        return {
            'total': total_count,
            'updated': updated_count,
            'failed': failed_count
        }

if __name__ == "__main__":
    # Run the update function when script is executed directly
    update_article_images()