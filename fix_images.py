import os
import logging
from flask import Flask
from models import db, Article

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
}

db.init_app(app)

def fix_article_images():
    """Update all article images to use improved SVG placeholders"""
    # Import the placeholder generator
    from main import generate_placeholder_image
    
    with app.app_context():
        # Use session.no_autoflush to avoid errors with loading relationships
        with db.session.no_autoflush:
            # First get all articles without loading keywords relation
            articles = Article.query.all()
            count = 0
            
            for article in articles:
                # Use a shortened title instead of keywords to avoid relationship loading issues
                keyword_text = article.title[:20] if article.title else "News"
                source_text = article.source[:10] if article.source else "unknown"
                
                # Generate a new placeholder image for each article using simpler params
                article.image_url = generate_placeholder_image(keyword_text, source_text)
                
                count += 1
                if count % 20 == 0:
                    # Commit in smaller batches to avoid timeouts
                    db.session.commit()
                    logging.info(f"Updated {count} articles...")
            
            # Commit any remaining changes
            db.session.commit()
            logging.info(f"Updated {count} articles with new SVG placeholder images")

if __name__ == "__main__":
    logging.info("Starting image fix process...")
    fix_article_images()
    logging.info("Image fix complete!")