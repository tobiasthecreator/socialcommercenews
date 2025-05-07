from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Create SQLAlchemy instance
db = SQLAlchemy()

class Keyword(db.Model):
    """Model for tracking news keywords."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with articles
    articles = db.relationship('Article', secondary='article_keyword', backref='keywords', lazy=True)
    
    def __repr__(self):
        return f'<Keyword {self.name}>'

class Article(db.Model):
    """Model for storing news articles."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(1024), nullable=False, unique=True)  # Increased from 512 to 1024 to handle longer URLs
    source = db.Column(db.String(100))
    published_date = db.Column(db.DateTime)
    content = db.Column(db.Text)
    summary = db.Column(db.Text)
    image_url = db.Column(db.String(1024), nullable=True)  # URL to the article's main image
    collected_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Article {self.title}>'

# Association table for many-to-many relationship between articles and keywords
article_keyword = db.Table('article_keyword',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('keyword_id', db.Integer, db.ForeignKey('keyword.id'), primary_key=True)
)